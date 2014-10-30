import unittest
import asyncio
import aiohttp
import json
import koa.core
import koa.common
import pdb

# spawns a temporary local test server, executes HTTP requests against it
class KoaTestSession:
  
  def __init__(self, app):
    self.app = app
    self.port = 8481

  # param test is a coroutine that can call self.request('get', '/foo')
  # and assert on the responses
  def run_async_test(self, test):
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    @asyncio.coroutine
    def coro():
      srv = yield from loop.create_server(self.app.get_http_request_handler, '0.0.0.0', self.port)
      try:
        yield from test
      finally:
        yield srv.close()

    loop.run_until_complete(coro())
    loop.close()

  # param method like 'GET' or 'POST'
  # param route like '/foo/123'
  @asyncio.coroutine
  def request(self, method, route, **kwargs):
    response = yield from aiohttp.request(method, 'http://127.0.0.1:{}{}'.format(self.port, route), **kwargs)
    return response


class KoaAppTestCase(unittest.TestCase):

  def test_app_with_no_routes_defined_yields_404(self):

    app = koa.core.app()

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/foo')
      response_text = yield from response.text()
      self.assertEqual(response.status, 404)
      self.assertEqual(response_text, "no response for method=GET path=/foo") # or some other decent msg

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_exception_in_middleware_yields_response_500(self):

    @asyncio.coroutine
    def middleware(koa_context, next):
      raise Exception('something something')

    app = koa.core.app()
    app.use(middleware)

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/baz')
      self.assertEqual(response.status, 500)
      response_text = yield from response.text()
      self.assertEqual(response.headers['CONTENT-TYPE'], 'text/html; charset=utf-8')
      self.assertTrue(response_text.find('something something') != -1) # probably don't want this for production builds, only debug

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_router_http_get_json(self):

    @asyncio.coroutine
    def handle_get(koa_context, next):
      koa_context.response.body = {'foo' : 'bar', 'bla': 7}
      # optionally here we could 'yield from next' but koa makes sure this is being done automatically even if we forget

    app = koa.core.app()
    router = koa.common.router()
    router.get("/baz", handle_get)
    app.use(router.middleware())

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/baz')
      response_json = yield from response.json()
      self.assertEqual(response.status, 200)
      self.assertEqual(response.headers['CONTENT-TYPE'], 'application/json')
      self.assertEqual(response_json, {"foo": "bar", "bla": 7})

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_router_http_get_text(self):

    @asyncio.coroutine
    def handle_get(koa_context, next):
      koa_context.response.body = "hello world<br/>"

    app = koa.core.app()
    router = koa.common.router()
    router.get("/baz", handle_get)
    app.use(router.middleware())

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/baz')
      response_text = yield from response.text()
      self.assertEqual(response.status, 200)
      self.assertEqual(response.headers['CONTENT-TYPE'], 'text/html')
      self.assertEqual(response_text, "hello world<br/>")

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_router_http_get_bytes(self):

    @asyncio.coroutine
    def handle_get(koa_context, next):
      koa_context.response.body = "hello world".encode('utf8')

    app = koa.core.app()
    router = koa.common.router()
    router.get("/baz", handle_get)
    app.use(router.middleware())

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/baz')
      response_bytes = yield from response.read()
      self.assertEqual(response.status, 200)
      self.assertEqual(response.headers['CONTENT-TYPE'], 'application/octet-stream')
      self.assertEqual(response_bytes, "hello world".encode('utf8'))

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_router_http_post(self):

    @asyncio.coroutine
    def handle_post(koa_context, next):
      koa_context.response.body = "hello world"

    app = koa.core.app()
    router = koa.common.router()
    router.post("/baz", handle_post)
    app.use(router.middleware())

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('post', '/baz') # no payload is posted, kinda unrealistic
      response_text = yield from response.text()
      self.assertEqual(response.status, 200)
      self.assertEqual(response.headers['CONTENT-TYPE'], 'text/html')
      self.assertEqual(response_text, "hello world")

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_router_http_get_with_query_params(self):

    @asyncio.coroutine
    def handle_get(koa_context, next):
      arg = koa_context.request.query['arg'][0]
      other = koa_context.request.query['other'][0]
      self.assertEqual(arg, '7')
      self.assertEqual(other, 'foo')
      koa_context.response.body = "hello " + other

    app = koa.core.app()
    router = koa.common.router()
    router.get("/baz", handle_get)
    app.use(router.middleware())

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/baz', params = {'arg':7, 'other':'foo'})
      response_text = yield from response.text()
      self.assertEqual(response.status, 200)
      self.assertEqual(response.headers['CONTENT-TYPE'], 'text/html')
      self.assertEqual(response_text, "hello foo")

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_router_http_get_with_route_params(self):

    @asyncio.coroutine
    def handle_get(koa_context, next):
      id = koa_context.request.params['id']
      self.assertEqual(id, '123')
      koa_context.response.body = "hello " + id

    app = koa.core.app()
    router = koa.common.router()
    router.get("/users/:id", handle_get)
    app.use(router.middleware())

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/users/123')
      response_text = yield from response.text()
      self.assertEqual(response.status, 200)
      self.assertEqual(response.headers['CONTENT-TYPE'], 'text/html')
      self.assertEqual(response_text, "hello 123")

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_router_http_get_with_route_params_mismatch_suffix(self):

    @asyncio.coroutine
    def handle_get(koa_context, next):
      koa_context.response.body = "hello"

    app = koa.core.app()
    router = koa.common.router()
    router.get("/users/:id", handle_get)
    app.use(router.middleware())

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/users/123/name')
      response_text = yield from response.text()
      self.assertEqual(response.status, 404)

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_router_http_get_with_route_params_mismatch_prefix(self):

    @asyncio.coroutine
    def handle_get(koa_context, next):
      koa_context.response.body = "hello"

    app = koa.core.app()
    router = koa.common.router()
    router.get("/users/:id", handle_get)
    app.use(router.middleware())

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/users')
      response_text = yield from response.text()
      self.assertEqual(response.status, 404)

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_mount_composition(self):

    @asyncio.coroutine
    def handle_get(koa_context, next):
      koa_context.response.body = "hello world"

    def get_nestable_app():
      app = koa.core.app()
      router = koa.common.router()
      router.get("/baz", handle_get)
      app.use(router.middleware())
      return app

    app = koa.core.app()
    nested_app = get_nestable_app()
    app.use(koa.common.mount('/nested', nested_app.middleware())) 

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/nested/baz')
      response_text = yield from response.text()
      self.assertEqual(response.status, 200)
      self.assertEqual(response.headers['CONTENT-TYPE'], 'text/html')
      self.assertEqual(response_text, "hello world")

      response404 = yield from test_session.request('get', '/baz')
      self.assertEqual(response404.status, 404)

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_body_parser_http_post_json(self):

    @asyncio.coroutine
    def handle_post(koa_context, next):
      assert isinstance(koa_context.request.body, dict) # POSTed JSON
      self.assertEqual(koa_context.request.body, {"foo":7})
      koa_context.response.body = "got it"

    app = koa.core.app()
    app.use(koa.common.body_parser)
    router = koa.common.router()
    router.post("/baz", handle_post)
    app.use(router.middleware())

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('post', '/baz', 
        data = json.dumps({"foo":7}),
        headers = {'content-type': 'application/json'}
      )
      response_text = yield from response.text()
      self.assertEqual(response.status, 200)
      self.assertEqual(response.headers['CONTENT-TYPE'], 'text/html')
      self.assertEqual(response_text, "got it")

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_static_returns_file_content(self):

    app = koa.core.app()
    app.use(koa.common.static('./testdata'))

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/foo/bar.txt')
      response_bytes = yield from response.read()
      self.assertEqual(response.status, 200)
      self.assertEqual(response.headers['CONTENT-TYPE'], 'application/octet-stream')
      self.assertEqual(response_bytes, "content of bar.txt".encode('utf8'))

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_mounted_koa_static_returns_file_content(self):

    app = koa.core.app()
    app.use(koa.common.mount('/data', koa.common.static('./testdata')))

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/data/foo/bar.txt')
      response_bytes = yield from response.read()
      self.assertEqual(response.status, 200)
      self.assertEqual(response.headers['CONTENT-TYPE'], 'application/octet-stream')
      self.assertEqual(response_bytes, "content of bar.txt".encode('utf8'))

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_logger(self):
    app = koa.core.app()
    app.use(koa.common.logger)

    @asyncio.coroutine
    def test():
      response = yield from test_session.request('get', '/foo')
      response_text = yield from response.text()
      self.assertEqual(response.status, 404)
      # note this test didn't verify anything actually got logged, kinda lame

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_koa_auth(self):
    app = koa.core.app()

    # this is not a middleware, it's just a regular coroutine returning a bool
    @asyncio.coroutine
    def my_credential_validator(user, password):
      return user == 'foo' and password == 'secret'

    # this is middleware that is supposed to be basic-auth-protected
    @asyncio.coroutine
    def my_middleware(koa_context, next):
      koa_context.response.body = "hi"

    app.use(koa.common.basic_auth(my_credential_validator))
    app.use(my_middleware)

    @asyncio.coroutine
    def test():

      # test successful auth
      response = yield from test_session.request('get', '/foo', auth = aiohttp.helpers.BasicAuth('foo', 'secret', 'utf-8'))
      responseText = yield from response.text()
      self.assertEqual(response.status, 200)
      self.assertEqual(responseText, "hi")

      # test wrong pass
      response = yield from test_session.request('get', '/foo', auth = aiohttp.helpers.BasicAuth('foo', 'wrong pass', 'utf-8'))
      self.assertEqual(response.status, 401)

      # test missing auth
      response = yield from test_session.request('get', '/foo')
      self.assertEqual(response.status, 401)

    test_session = KoaTestSession(app)
    test_session.run_async_test(test())

  def test_verify_is_middleware_passes_for_decorated_coro(self):
    @asyncio.coroutine
    def f(context, next):
      yield from next
    koa.core.verify_is_middleware(f)

  def test_verify_is_middleware_passes_for_decorated_func(self):
    @asyncio.coroutine
    def f(context, next):
      pass  # no explicit yield
    koa.core.verify_is_middleware(f)

  def test_verify_is_middleware_detects_missing_decorator_on_generator(self):
    def f(context, next):
      yield from next
    with self.assertRaises(Exception) as cm:
      koa.core.verify_is_middleware(f)
    self.assertEqual("argument is not middleware: is a generator function (caller try to add @asyncio.coroutine decorator)", str(cm.exception))

  def test_verify_is_middleware_detects_missing_decorator_on_func(self):
    def f(context, next):
      pass
    with self.assertRaises(Exception) as cm:
      koa.core.verify_is_middleware(f)
    self.assertEqual("argument is not middleware: is a function (caller try to add @asyncio.coroutine decorator)", str(cm.exception))

  def test_verify_is_middleware_detects_None(self):
    with self.assertRaises(Exception) as cm:
      koa.core.verify_is_middleware(None)
    self.assertEqual("argument is not middleware: None", str(cm.exception))

  def test_verify_is_middleware_detects_coro_object(self):
    @asyncio.coroutine
    def f(context, next):
      yield from next
    with self.assertRaises(Exception) as cm:
      koa.core.verify_is_middleware(f(None, None))
    self.assertEqual("argument is not middleware: is a generator object (caller try to remove parens)", str(cm.exception))

  def test_verify_is_middleware_detects_missing_call_to_member(self):
    router = koa.common.router()
    with self.assertRaises(Exception) as cm:
      koa.core.verify_is_middleware(router)
    self.assertEqual("argument is not middleware: is has a member middleware() though (try to call it)", str(cm.exception))
