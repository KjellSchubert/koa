import asyncio
import os
import koa.core
import koa.common

# handles get /admin/version
@asyncio.coroutine
def handle_get_version(koa_context, next):
  koa_context.response.body = "0.1.5"

def create_app():
  # compose the koa app
  app = koa.core.app()
  app.use(koa.common.logger)
  router = koa.common.router()
  router.get("/admin/version", handle_get_version)
  app.use(router.middleware())
  return app

def run_server_forever():
  
  # compose the koa app
  app = create_app()

  # serve the koa app via asyncio http server
  loop = asyncio.get_event_loop()
  port = int(os.environ.get('PORT', 8480)) # for Heroku, which sets env var PORT before it spawns your web process
  srv = loop.run_until_complete(loop.create_server(app.get_http_request_handler, '0.0.0.0', port))
  print('serving on', srv.sockets[0].getsockname())
  try:
    loop.run_forever()
  except KeyboardInterrupt:
    pass

if __name__ == '__main__':
  run_server_forever()

# To test the server run these commands:
# >curl --verbose localhost:8480/admin/version
#    Handled by handle_get_version()
# >curl --verbose localhost:8480/foo
#    This should yield 404.
