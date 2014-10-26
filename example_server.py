from urllib.parse import urlparse, parse_qsl

import asyncio
import aiohttp
import aiohttp.server
import os
import pdb
import koa.core
import koa.common

users = [{'name': 'testuser' + str(id)} for id in range(0,3)]

# koajs-style handling of HTTP GET requests for the /users route
@asyncio.coroutine
def handle_get_users(koa_context, next):
  query = koa_context.request.query
  # simple paging to demo the handling of query params:
  start_id = int(query['start_id'][0]) if 'start_id' in query else 0  # paging via /users?start_id=123
  page_size = 6
  koa_context.response.body = [users[id] for id in range(start_id, min(start_id + page_size, len(users)))]

# handles /users:id
@asyncio.coroutine
def handle_get_user(koa_context, next):
  id = int(koa_context.request.params.id)
  if not (0 <= id and id < len(users)):
    koa_context.response.status = 404
    koa_context.response.body = "out of range"
    return
  koa_context.response.body = users[id]

# handles post to /users
@asyncio.coroutine
def handle_post_user(koa_context, next):
  user = koa_context.request.body    # this requires app.use(koa.common.body_parser)
  assert(isinstance(user, dict)) # POSTed JSON
  print("posted user:", user)
  users.append(user)
  koa_context.response.body = "OK"

# return a koa app (to demo composition of apps)
def create_users_app():
  app = koa.core.app()
  router = koa.common.router()
  router.get("/users", handle_get_users)
  router.get("/users/:id", handle_get_user)
  router.post("/users", handle_post_user)
  app.use(router.middleware())
  return app


# handles get /admin/version
@asyncio.coroutine
def handle_get_version(koa_context, next):
  koa_context.response.body = "0.1.5"

def create_app():
  # compose the koa app
  app = koa.core.app()
  app.use(koa.common.logger)
  app.use(koa.common.body_parser)
  router = koa.common.router()
  router.get("/admin/version", handle_get_version)
  app.use(router.middleware())
  app.use(koa.common.mount('/data', koa.common.static('./testdata'))) # serves all content from dir './testdata' under path '/data', so this serves HTTP GET requests like /data/foo/bar.txt, which will return the content of file /testdata/foo/bar.txt

  # demonstrate composition of koa apps:
  app.use(koa.common.mount('/admin', create_users_app().middleware())) # allows for HTTP GET /admin/users
  
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
# >curl localhost:8480/admin/users
#       This lists the original set of users.
# >curl -X POST -H "Content-Type: application/json" -d "{\"name\":\"easterbunny\"}" http://localhost:8480/admin/users
#       This appends a new user to the list of users.
# >curl localhost:8480/admin/users
#       To list the original & posted users.
# >curl "localhost:8480/admin/users?start_id=2"
#       To use paging for listing users.
# >curl localhost:8480/data/foo/bar.txt
# >curl localhost:8480/data/xyz.dat
#       To exercise koa-static's file serving.