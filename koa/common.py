# this is the sort of middleware as implemented by https://www.npmjs.org/package/koa-common
# and its individual dependencies (like https://www.npmjs.org/package/koa-logger,
# https://www.npmjs.org/package/koa-mount and so on). The koa.js devs explicitly split
# koa's core and koa-common into two separate npm packages, with koa-common koa bundling
# independent middleware like logger() and static() simply for convenience's sake (for
# devs used to express.js providing the same bundle to them). I didn't bother doing that
# koa vs koa-common split here, instead I keep both koa and koa-common in the same python package.

import asyncio
import aiohttp
import time
import pdb
import json
import os
import os.path
import urllib

# koa.js-style middleware for logging request handling times.
# Similar to https://www.npmjs.org/package/koa-logger and https://www.npmjs.org/package/koa-response-time
@asyncio.coroutine
def logger(koa_context, next):
  start_time = time.clock()
  print("request method={} path={}".format(koa_context.request.method, koa_context.request.path.path))
  yield from next
  end_time = time.clock()
  print("request method={} path={} completed after {} ms".format(koa_context.request.method, koa_context.request.path.path, round((end_time-start_time) * 1000)))

# middleware similar to https://www.npmjs.org/package/koa-body-parser
# Reads the aiohttp.streams.FlowControlStreamReader payload storing the result 
# in koa_context.request.body. 
# Parses payload as JSON if "Content-Type: application/json".
# Example curl: curl --verbose -X POST -H "Content-Type: application/json" -d '{"foo":"xyz","bar":"xyz"}' http://localhost:8480/effective_config
@asyncio.coroutine
def body_parser(koa_context, next):
  request = koa_context.request
  if request.method in ["POST", "PUT"]:   # though I guess even a GET request could have a payload? TODO

    # Should we use aiohttp.protocol.HttpPayloadParser instead? How? Doing it manually for now:
    lines = []
    for i in range(0,10):
      line = yield from koa_context.request.payload.readline()
      if len(line) == 0:
        break # is the the proper EOS?
      lines.append(line.decode('utf8'))
    payload_string = "".join(lines)
    koa_context.request.body = json.loads(payload_string) if request.headers.get('CONTENT-TYPE') == 'application/json' else payload_string
    #print("stored payload in request.body:", koa_context.request.body)

  yield from next

# Like https://www.npmjs.org/package/koa-static, so this can serve individual files
# or whole directory trees.
# param file_or_dir_path is the file or dir to be served. For example if you pass a
# 'mydir' and this contains these files:
#    mydir/
#    mydir/foo/bar.txt
#    mydir/xyz.dat
# then static('mydir') will serve HTTP GET requests with paths '/foo/bar.txt' and '/xyz.dat'.
# Usually you'll use mount() to mount this middleware under a parent path.
# Also remember you may serve static content faster via reverse proxies like nginx.
def static(file_or_dir_path):

  def split_path(p):
    a,b = os.path.split(p)
    return (split_path(a) if len(a) and len(b) else []) + [b]

  def is_valid_path_component(path_component):
    return len(path_component) > 0 and path_component != '..'

  # ensure client does not request /../../system/passwords
  # In general '..' is illegal in requests
  # param like 'foo/bar.txt'
  # TODO: not safe enough for production envs atm!
  def ensure_is_valid_path(p):
    path_components = split_path(p)
    for component in path_components:
      if not is_valid_path_component(component):
        raise Exception("invalid component '{}' in path {}" + p)

  def strip_leading_slash(file_name):
    return file_name[1:] if file_name.startswith('/') else file_name

  # for running sync I/O in a threadpool
  def run_async(func):
    # this first approach here doesn't work:
    #   return asyncio.async(asyncio.coroutine(func)())
    # since it blocks the loop while executing the func.
    # This here does work, but WARNING: if you have a lot of parallel slow I/O
    # tasks then the threadpool will still become a bottle neck!
    # Someone please impl true (nodejs-style) async file io for Python :)
    return asyncio.get_event_loop().run_in_executor(None, func)

  if os.path.isfile(file_or_dir_path):
    raise Exception("static() does not support serving individual files atm, only dirs: " + file_or_dir_path)
  if not os.path.isdir(file_or_dir_path):
    raise Exception("static() dir {} does not exist".format(file_or_dir_path))

  # This here is the koa middleware that does the actual file reading
  @asyncio.coroutine
  def static_middleware(koa_context, next):
    # There's nothing fancy like caching addressed in this impl, it's minimalist. TODO?
    # Also note how nodejs makes it difficult to accidentally call sync I/O methods in
    # coroutines (or anywhere) since the nodejs file IO is async alrdy (with the exception
    # of the explicitly name *sync methods like http://nodejs.org/api/fs.html#fs_fs_readfilesync_filename_options)
    # whereas in Python you have to be careful to asyncify Python's sync file I/O to not
    # accidentally turn you C10k server into a C10 one :)
    # See https://docs.python.org/3/library/asyncio-dev.html#handle-blocking-functions-correctly
    # and https://gist.github.com/kunev/f83146d407c81a2d64a6
    relative_file_name = strip_leading_slash(koa_context.request.path.path)
    ensure_is_valid_path(relative_file_name)
    requested_file_name = os.path.join(file_or_dir_path, relative_file_name)
    does_request_file_exist = yield from run_async(lambda: os.path.isfile(requested_file_name))
    if does_request_file_exist:
      # TODO: use streaming here instead of reading the file in one large chunk, which
      # works poorly even for moderately large files

      read_chunk_size_in_bytes = yield from run_async(lambda: os.stat(requested_file_name).st_size)
      try:   # os.open does not support 'with'? :(
        request_file_handle = yield from run_async(lambda: os.open(requested_file_name, os.O_RDONLY))

        # The disk I/O could be slow. To verify that slow file IO really does not block 
        # your event loop try this:
        #    yield from run_async(lambda: time.sleep(5))

        bytes_read = yield from run_async(lambda: os.read(request_file_handle, read_chunk_size_in_bytes))
      finally:
        yield from run_async(lambda: os.close(request_file_handle))
      koa_context.response.body = bytes_read

  return static_middleware

# Mounts middleware under a parent_path, like https://www.npmjs.org/package/koa-mount.
# So if for example you have the static('mydir') middleware serving '/foo/bar.txt' then
# mount('/data/stuff/', static('mydir')) will serve bar.txt for HTTP GET request path
# /data/stuff/foo/bar.txt
# It's OK to pass parent_path='/', which allows you to mount several middleware under
# the same root.
# Note how router() could be composed of mount() plus a request method matcher.
# Usage: app.use(koa.common.mount('/foo', middleware))
def mount(parent_path, middleware):
  # Quote https://www.npmjs.org/package/koa-mount 'The path passed to mount() is stripped 
  # from the URL temporarily until the stack unwinds. This is useful for creating entire 
  # apps or middleware that will function correctly regardless of which path segment(s) 
  # they should operate on.'
  assert parent_path.startswith('/'), 'mount path must begin with "/"'

  if parent_path.endswith('/'):
    parent_path = parent_path[0:-1] # strip trailing slash to normalize prefix (if parent_path was '/' to begin with then it's an empty string now)
  
  # return None if prefix doesnt match
  def get_remaining_path_suffix(path):
    if not path.startswith(parent_path):
      return None
    suffix = path[len(parent_path):]
    if len(suffix) > 0 and suffix[0] != '/':
      return None  # /mount does not match /mountlkjalskjdf
    return suffix

  @asyncio.coroutine
  def mount_middleware(koa_context, next):
    orig_path = koa_context.request.path
    remaining_path_suffix = get_remaining_path_suffix(orig_path.path)

    @asyncio.coroutine
    def nop():
      pass

    if remaining_path_suffix == orig_path.path:

      # optional optimization for mounting at '/': just call the middleware without modifying the path
      yield from middleware(koa_context, nop())

    elif remaining_path_suffix != None:   # otherwise the prefix doesn't match, just call next handler then

      koa_context.request.path = urllib.parse.ParseResult(orig_path.scheme, orig_path.netloc, remaining_path_suffix, orig_path.params, orig_path.query, orig_path.fragment)
      try:
        yield from middleware(koa_context, nop())  # mounted middleware executes with remaining path suffix
      finally:
        koa_context.request.path = orig_path

    yield from next

  return mount_middleware

# c'tor func returning a KoaRouter instance (Crockford-style private classes and funcs).
# On KoaRouter you register HTTP routes (matching request paths) together with HTTP request
# method names (POST, GET, PUT, ...) and map them to your request handler. That allows
# you to supply individual handlers for each kind of route in your REST API.
def router():

  # some middleware doesn't want to explicitly do a 'yield from next', so let's auto-yield
  # to the next middleware, draining the generator.
  @asyncio.coroutine
  def ensure_we_yield_to_next(middleware, next):
    assert middleware != None, "middleware generator is None, maybe you forgot a @asyncio.coroutine decorator on middleware?"
    yield from middleware
    yield from next # if the middleware did 'yield from next' then this here is a NOP

  # like the specs for https://github.com/alexmingoia/koa-router, so represent routes like '/users/:id'
  class ExpressJsStyleRoute:
    def __init__(self, route):
      self.path = route
      self.path_components = route.split('/')
      if len(self.path_components)==0 or self.path_components[0] != '':
        raise Exception("routes must start with a '/'")
  
    # ExpressJsStyleRoute('/users/:id').matches('/users/123') should return {id: 123}
    # ExpressJsStyleRoute('/users').matches('/users') should return {}
    # ExpressJsStyleRoute('/users').matches('/foo') should return None for mismatch
    # ExpressJsStyleRoute('/users/:id').matches('/users') should return None for mismatch
    # ExpressJsStyleRoute('/users/:id/name').matches('/users/123') should return None for mismatch
    def matches(self, path):
      if path == self.path:
        return {}
      path_components = path.split('/')
      if len(path_components) != len(self.path_components):
        return None
      params = {}
      for i in range(0, len(path_components)):
        actual = path_components[i]
        expected = self.path_components[i]
        if actual == expected:
          continue
        elif expected.startswith(':'):
          param_name = expected[1:] # e.g. ':id' maps to param_name='id'
          params[param_name] = actual
        else:
          return None # mismatch
      return params
  
  # represents a route added via KoaRouter.get, so the URL path matcher,
  # the HTTP method (GET vs POST vs ...) and the coroutine for handling
  # the matched requests.
  class KoaRoute:
    # param HTTP method like "GET"
    # param path like "/config"
    # param handler is koajs middleware (so a coroutine taking KoaContext and next)
    def __init__(self, method, path, handler):
      self.method = method
      self.path = ExpressJsStyleRoute(path)
      self.handler = handler

  # Mimics https://www.npmjs.org/package/koa-router, so does express.js-style
  # routing of HTTP requests via router.get('/users/:id', handle_get_users_byid)
  # or router.post('/users', handle_post_users), with your handlers being
  # coroutines.
  class KoaRouter():
  
    def __init__(self):
      self._routes = []  # list of KoaRoute instances

    # param handler is a coroutine to handle the HTTP GET request.
    # Your coroutine gets the same args as any other koa-style middleware:
    # a KoaContext and the 'next' middleware.
    def get(self, path, handler):
      self._routes.append( KoaRoute("GET", path, handler) )

    # Same as get(), but matches HTTP POST requests.
    def post(self, path, handler):
      self._routes.append( KoaRoute("POST", path, handler) )

    # Same as get(), but matches HTTP PUT requests.
    def put(self, path, handler):
      self._routes.append( KoaRoute("PUT", path, handler) )

    # Same as get(), but matches HTTP DELETE requests.
    def delete(self, path, handler):
      self._routes.append( KoaRoute("DELETE", path, handler) )

    # this func returns koajs middleware (so it returns a coroutine func),
    # which is epxected to be passed to KoaApp.use()
    def middleware(self):
      @asyncio.coroutine
      def inner(context, next):
        # Execute handlers in order in which they're registered (only makes a difference
        # if a path matches several different handlers, which should be avoided).
        # Note that this execution loop here is very similar to KoaHttpRequestHandler.handle_request,
        # with the difference being an extra filter/predicate that determines if the route
        # matches or not.
        for i in reversed(range(len(self._routes))):
          route = self._routes[i]
          if route.method == context.request.method:
            params = route.path.matches(context.request.path.path)
            does_route_match = params != None
            if does_route_match:
              context.request.params = params
              middleware = route.handler(context, next)
              assert middleware != None, "did you forget @asyncio.coroutine on the handler for route {} {}?".format(route.method, route.path.path)
              next = ensure_we_yield_to_next(middleware, next)
        yield from next
      return inner

  return KoaRouter()