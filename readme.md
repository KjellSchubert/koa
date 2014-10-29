Koa.js web framework port for asyncio + aiohttp
====

[![Build Status](https://travis-ci.org/KjellSchubert/koa.svg?branch=master)](https://travis-ci.org/KjellSchubert/koa)
[![Coverage Status](https://coveralls.io/repos/KjellSchubert/koa/badge.png?branch=master)](https://coveralls.io/r/KjellSchubert/koa?branch=master)

[express.js](https://www.npmjs.org/package/express) is probably the most commonly used web framework 
for [node.js](http://nodejs.org/), with Express being the 'E' in the [MEAN](http://en.wikipedia.org/wiki/MEAN) 
stack. [Koa.js](https://www.npmjs.org/package/koa) is the coroutine-based successor framework for Express, 
created by the same team that created & maintains Express. See [here](http://strongloop.com/strongblog/node-js-express-introduction-koa-js-zone/) for an introduction to Koa.

Over the last years we've seen a convergence of async programming
abstractions across programming languages, e.g. for Javascript & Python we'v seen this convergence 
for [promises/Futures](https://github.com/KjellSchubert/promise-future-task) and for 
[generators/coroutines](https://github.com/KjellSchubert/coroutines-python-javascript) (as the basis for 
.NET-style async/await). Having used
both Express & Koa before in nodejs applications I was wondering if I could implement the equivalent of 
Koa.js for Python based on asyncio. This here is an [aiohttp](https://pypi.python.org/pypi/aiohttp)-based
implementation of a Koa-style web microframework.
Mostly this project was an opportunity for me to play with Python coroutines.
I wouldn't have bothered with that exercise if there already had been a Koa-style minimalist web 
framework in Python (supporting composition of apps and middleware), but I couldn't find one. 
Tell me if you know of one. Frameworks I am aware of are:

* Tornado (seem to require a [bridge](http://tornado.readthedocs.org/en/latest/asyncio.html) to asyncio, middleware is different)
* aiohttp (based on asyncio, but has no concept of an app/Application as of 0.9, this is planned for 0.10)
* Twisted (no Python 3 support atm)

Requirements
---
* Python >= 3.4
* [aiohttp](https://pypi.python.org/pypi/aiohttp/) >= 0.9.2

Middleware
---

For express.js middleware is simply a function taking params request, response and next (see
tutorial [here](https://blog.safaribooksonline.com/2014/03/10/express-js-middleware-demystified/) for details).
So middleware for express.js looks like this:

    function(req, res, next) {
      res.send('Hello World!');
    }

What's also important is that an express.js app itself is middleware, this allows you to compose an app of
both middleware and other apps. 

Koa.js as the successor to express.js uses the same style with two modifications: 

* middleware is a coroutine, not a function
* the request & response params are combined into a single param 'context' which has response & request as members
* the context is passed via param 'this', no longer as a method param

So Koa.js style middleware (in Javascript) looks like this:

    function *(next){
      this; // is the Context
      this.request; // is a koa Request
      this.response; // is a koa Response
      yield next;
      doOtherStuff();
    }

When porting this scheme to Python I decided to create a hybrid of the express.js and koa.js middleware schemes:

* passing the context via 'this' or self would probably seem funky to Python devs, so I don't pass the 
  context via 'this' this but as regular param. So where express.js passed (req, response, next) I pass
  (context, next), with the context having request & response members.
* in asyncio.io coroutines I cannot write 'yield next', but have to use 'yield from next'

So (Python-style) Koa middleware looks like this:

    @asyncio.coroutine
    def my_middleware(koa_context, next):
      request = koa_context.request
      response = koa_context.response
      yield from next
      doOtherStuff()

Documentation
---

Fail. I didn't create any yet. Since I'm trying to mimic koa.js as closely as possibe see [Koa](http://koajs.com/)
for documentation, atm not everything maps to Python exactly as listed in the koa.js docu (TODO). The closest
I have to documentation atm are the examples & tests.

Example apps:
---
For a simple example server see example_server_simple.py, which uses koa-logger and koa-router.
For a slightly more complex example see example_server.py: this demonstrates koa-static, koa-mount and HTTP POSTs.
Here the full content of example_server_simple.py:

    import asyncio
    import koa.core
    import koa.common
    
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

      # serve the koa app via asyncio http server
      loop = asyncio.get_event_loop()
      loop.run_until_complete(loop.create_server(create_app().get_http_request_handler, '0.0.0.0', 8480))
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
