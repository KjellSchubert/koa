import asyncio
import aiohttp
import aiohttp.server
import urllib
import json
import pdb
import inspect

# Creates koa app. Call app.use() to connect middleware coroutines.
def app():

  # param writer is self.writer of aiohttp.server.ServerHttpProtocol
  # param message is the original message the response is for
  # response_jso is a dict() to be sent as json
  @asyncio.coroutine
  def send_http_response_json(writer, message, response_jso, status_code):
    response_text = json.dumps(response_jso)
    yield from send_http_response_text_utf8(writer, message, 'application/json', response_text, status_code)

  @asyncio.coroutine
  def send_http_response_text(writer, message, response_text, status_code):
    yield from send_http_response_text_utf8(writer, message, 'text/html', response_text, status_code)

  @asyncio.coroutine
  def send_http_response_text_utf8(writer, message, content_type, response_text, status_code):
    responsebytes = response_text.encode("utf-8")
    yield from send_http_response(writer, message, content_type, responsebytes, status_code)

  # param content_type e.g. 'application/json'
  @asyncio.coroutine
  def send_http_response(writer, message, content_type, response_bytes, status_code):
    assert isinstance(response_bytes, bytes)
    response = aiohttp.Response(
        writer, status_code, http_version=message.version
    )
    response.add_header('Content-Type', content_type)
    response.add_header('Content-Length', str(len(response_bytes))) # len encoded bytes
    response.send_headers()
    response.write(response_bytes)
    #print("response.write wrote {} bytes".format(len(response_bytes)))
    yield from response.write_eof()

  class KoaRequest:
    # param message is the message passed to aiohttp.server.ServerHttpProtocol.handle_request()
    def __init__(self, message):
      # these props attemp to stick closely to koajs request
      self.method = message.method
      self.headers = message.headers
      self.path = urllib.parse.urlparse(message.path)
      self.querystring = self.path.query
      self.query = urllib.parse.parse_qs(self.querystring)
    
      self._message = message   # not part of koajs, just in case some middleware needs it

  class KoaResponse:
    def __init__(self):
      self.status = None # 200, 404, ...
      self.body = None # {}, string, ...

  class KoaContext:
    # param message is the message passed to aiohttp.server.ServerHttpProtocol.handle_request()
    def __init__(self, message):
      self.request = KoaRequest(message)
      self.response = KoaResponse()  # to be filled out by the middleware handlers

  @asyncio.coroutine
  def koa_write_response(koa_context):
    body = koa_context.response.body
    status_code = koa_context.response.status or 200
    writer = koa_context.response.writer
    message = koa_context.request._message
    if isinstance(body, dict) or isinstance(body, list):
      yield from send_http_response_json(writer, message, koa_context.response.body, status_code)
    elif isinstance(body, str):
      yield from send_http_response_text(writer, message, koa_context.response.body, status_code)
    elif isinstance(body, bytes):
      yield from send_http_response(writer, message, 'application/octet-stream', koa_context.response.body, status_code)
    elif koa_context.response.body != None:
      yield from send_http_response_text(writer, message, "unknown response type: {}".format(koa_context.response.body.__class__.__name__), status_code = 500)
    else:
      yield from send_http_response_text(writer, message, "no response for method={} path={}".format(koa_context.request.method, koa_context.request.path.path), status_code = 404)

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
      yield from self.middleware(context, next)

  # This stores the chain of middleware your app is composed of, executing this
  # chain for each incoming HTTP request
  class KoaApp():
   
    def __init__(self):
      self.middlewares = []  # coroutine funcs

    # wires up koa.js-style middleware
    # param middleware is a coroutine that will receive params (request, next)
    def use(self, middleware):
      assert callable(middleware), "middleware is supposed to be a (coroutine) function"
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