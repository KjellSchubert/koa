import asyncio
import aiohttp
import aiohttp.server
import urllib
import json
import pdb
import inspect
import types

# Creates koa app. Call app.use() to connect middleware coroutines.
def app():

  class KoaRequest:
    # param message is the message passed to aiohttp.server.ServerHttpProtocol.handle_request()
    def __init__(self, message):
      # these props attemp to stick closely to koajs request
      self.method = message.method
      self.headers = message.headers
      self.path = urllib.parse.urlparse(message.path)
      self.original_path = self.path   # koa.js lists an 'originalUrl' member, which stays the same even during chains of mount(), whereas path() will shrink for each mount() level
      self.querystring = self.path.query
      self.query = urllib.parse.parse_qs(self.querystring)
    
      self._message = message   # not part of koajs, just in case some middleware needs it

  class KoaResponse:
    def __init__(self):
      self.status = None # 200, 404, ...
      self.body = None # {}, string, ...
      self.type = None  # will be inferred from body unless you set it explicitly
      self.headers = [] # e.g. add tuples like ('Location', 'http://example.com/index.html')

  class KoaException(Exception):
    def __init__(self, message, status):
      self.message = message
      self.status = status

  class KoaContext:
    # param message is the message passed to aiohttp.server.ServerHttpProtocol.handle_request()
    def __init__(self, message):
      self.request = KoaRequest(message)
      self.response = KoaResponse()  # to be filled out by the middleware handlers

    # like ctx.throw() at http://koajs.com/
    def throw(self, message, status):
      raise KoaException(message, status)

    def redirect(self, relative_url):
      """ like koa.js context.redirect(), e.g. context.redirect('index.html')
      """
      # this here is kinda tricky when koa.common.mount is in effect: here we know 
      # we want a relative redirect from / to /index.html, but when we send the 301 
      # response we need the absolute location we are redirecting to.
      # So here we should try to avoid knowing under which abs path we're mounted
      base_path = self.request.original_path.path
      if not base_path.endswith('/'):
        base_path = base_path + '/'
      loc =  base_path + relative_url
      response = self.response
      response.status = 301
      response.headers.append( ['Location', loc] )
      response.body = 'redirect to <a href="{}">{}</a>'.format(loc, loc)

  def process_json_response(body, type, status):
    jso = body
    body = json.dumps(jso).encode('utf-8')
    type = type or 'application/json'
    status = status or 200
    return (body, type, status)
    
  def process_text_response(body, type, status):
    text = body
    body = text.encode('utf-8')
    type = type or 'text/html'
    status = status or 200
    return (body, type, status)

  def process_bytes_response(body, type, status):
    type = type or 'application/octet-stream'
    status = status or 200
    return (body, type, status)

  @asyncio.coroutine
  def koa_write_response(koa_context):
    request = koa_context.request
    response = koa_context.response
    headers = response.headers
    body = response.body
    status = response.status  # status code
    type = response.type      # ContentType
    writer = response.writer

    # transform all variants of body to bytes
    if isinstance(body, dict) or isinstance(body, list):
      (body, type, status) = process_json_response(body, type, status)
    elif isinstance(body, str):
      (body, type, status) = process_text_response(body, type, status)
    elif isinstance(body, bytes):
      (body, type, status) = process_bytes_response(body, type, status)
    elif body != None:
      msg = "unknown response type: {}".format(body.__class__.__name__)
      (body, type, status) = process_text_response(msg, 'text/html', 500)
    elif body == None and status != None:
      pass
    else:
      msg = "no response for method={} path={}".format(request.method, request.path.path)
      (body, type, status) = process_text_response(msg, 'text/html', 404)
    assert body == None or isinstance(body, bytes)
    assert type == None or isinstance(type, str)
    assert isinstance(status, int)

    http_response = aiohttp.Response(writer, status, http_version = request._message.version)
    for header in headers:
      assert len(header) == 2
      http_response.add_header(header[0], header[1])
      # e.g. http_response.add_header('WWW-Authenticate', 'Basic realm="Authorization Required"')
    if body != None:
      assert isinstance(body, bytes)
      http_response.add_header('Content-Type', type or 'application/octet-stream')
      http_response.add_header('Content-Length', str(len(body))) # len encoded bytes
    http_response.send_headers()
    if body != None:
      yield from http_response.write(body)
    yield from http_response.write_eof()

  # some middleware doesn't want to explicitly do a 'yield from next', so let's auto-yield
  # to the next middleware, draining the generator.
  @asyncio.coroutine
  def ensure_we_yield_to_next(middleware, next):
    yield from middleware
    yield from next # if the middleware did 'yield from next' then this here is a NOP

  # one of these will be instantiated per http request
  class KoaHttpRequestHandler(aiohttp.server.ServerHttpProtocol):

    # param middleware is a coroutine for handling the request, typically KoaApp().middleware()
    def __init__(self, middleware):
      aiohttp.server.ServerHttpProtocol.__init__(self, debug=True, keep_alive=75)
      self.middleware = middleware

    # this here is the request router
    @asyncio.coroutine
    def handle_request(self, message, payload):
      context = KoaContext(message)
      context.response.writer = self.writer
      context.request.payload = payload # is a aiohttp.streams.FlowControlStreamReader, use middleware.body_parser() to parse this as JSON
    
      # now process the chain of middlewares in order. Each middleware gets passed
      # its successor aka next as a coroutine, allowing nesting middleware, not just
      # plain sequential chaining.
      # This is the same mechanism koa.js uses for chaining & nesting middleware, I wonder
      # there's a more straightforward way to achieve the same.
      next = koa_write_response(context) # final one to execute, the only one that doesn't take a 'next' param
      try:
        yield from self.middleware(context, next)
      except KoaException as ex:
        # this here deals explicitly with exceptions thrown via KoaContext.throw(), e.g. thrown
        # by koa.common.basic_auth() to send a 401 without executing any remaining middleware.
        # Other kinda of exceptions are OK to bubble out of here, they should yield a 500
        context.response.status = ex.status
        context.response.body = ex.message
        yield from next # calls koa_write_response(context)
        

  # This stores the chain of middleware your app is composed of, executing this
  # chain for each incoming HTTP request
  class KoaApp():
   
    def __init__(self):
      self.middlewares = []  # coroutine funcs

    # wires up koa.js-style middleware
    # param middleware is a coroutine that will receive params (request, next)
    def use(self, middleware):
      verify_is_middleware(middleware)
      #assert len(inspect.getargspec(middleware).args) == 2, "middleware is supposed to be a coroutine function taking 2 args KoaContext and next"
      # TODO: assert that the func takes 2 params: koa_context and next
      self.middlewares += [middleware]

    # returns middleware that can be use()'ed in a different koa app, allowing
    # for app composition, usually via mount()
    def middleware(self):

      @asyncio.coroutine
      def inner(context, next):
        # now process the chain of middlewares in order. Each middleware gets passed
        # its successor aka next as a coroutine, allowing nesting middleware, not just
        # plain sequential chaining.
        # This is the same mechanism koa.js uses for chaining & nesting middleware, I wonder
        # there's a more straightforward way to achieve the same.
        for i in reversed(range(len(self.middlewares))):
          middleware = self.middlewares[i](context, next)
          next = ensure_we_yield_to_next(middleware, next)
        yield from next

      return inner

    # This is to be passed to loop.create_server()
    def get_http_request_handler(self):
      return KoaHttpRequestHandler(self.middleware())

  return KoaApp()

def verify_is_middleware(candidate):
  """ functiom that verifies that the given param meets the requirements for being koa-style middleware:
      mostly asyncio.iscoroutinefunction() taking 2 params (koa_context, next). Throws
      exception with some diagnostic info if this verification fails.
  """
  if not asyncio.iscoroutinefunction(candidate):
    if (inspect.isgeneratorfunction(candidate)):
      raise Exception("argument is not middleware: is a generator function (caller try to add @asyncio.coroutine decorator)")
    if asyncio.iscoroutine(candidate):
      raise Exception("argument is not middleware: is a generator object (caller try to remove parens)")
    if isinstance(candidate, types.GeneratorType):
      raise Exception("argument is not middleware: is a generator object (caller try to remove parens, add @asyncio.coroutine decorator)")
    if callable(candidate):
      raise Exception("argument is not middleware: is a function (caller try to add @asyncio.coroutine decorator)")
    if candidate == None:
      raise Exception("argument is not middleware: None")
    if hasattr(candidate, 'middleware'):
      if callable(candidate.middleware):
        raise Exception("argument is not middleware: is has a member middleware() though (try to call it)")
      raise Exception("argument is not middleware: is has a member middleware though (try to pass it)")
    raise Exception("argument is not middleware: type is '" + candidate.__class__.__name__ + "'")
  # TODO: verify that the coro func takes 2 params (koa_context, next)
  # see http://stackoverflow.com/questions/3972290/how-can-i-get-the-argument-spec-on-a-decorated-function
  # Atm I see ArgSpec(args=[], varargs='args', keywords='kw', defaults=None)