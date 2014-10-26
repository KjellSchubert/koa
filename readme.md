Koa.js web framework port for asyncio + aiohttp
====

[![Build Status](https://travis-ci.org/KjellSchubert/koa.svg?branch=master)](https://travis-ci.org/KjellSchubert/koa)
[![Coverage Status](https://coveralls.io/repos/KjellSchubert/koa/badge.png?branch=master)](https://coveralls.io/r/KjellSchubert/koa?branch=master)

[express.js](https://www.npmjs.org/package/express) is probably the most commonly used web framework 
for [node.js](http://nodejs.org/), with Express being the 'E' in the [MEAN](http://en.wikipedia.org/wiki/MEAN) 
stack. [Koa.js](https://www.npmjs.org/package/koa) is the coroutine-based successor framework for Express, 
created by the same team that created & maintains Express. See [here](http://strongloop.com/strongblog/node-js-express-introduction-koa-js-zone/) for an introduction to Koa.

Over the last years we've seen a convergence of async programming
abstractions across programming languages, e.g. for Javascript ([Promises/A+](https://promisesaplus.com/) and
[generators](http://wiki.ecmascript.org/doku.php?id=harmony:generators)) & Python
([asyncio](https://docs.python.org/3/library/asyncio.html) promises/futures and coroutines). Having used
both Express & Koa before in nodejs applications I was wondering if I could implement the equivalent of 
Koa for Python based on asyncio. This here is a proof of concept for such an 
asyncio/[aiohttp](https://pypi.python.org/pypi/aiohttp/)-based Koa implementation: like the original nodejs 
implementation of the minimalist Koa framework (with &lt; 1000 LOC) the Python implementation has &lt; 1000 LOC. 
Mostly this project was an opportunity for me to play with Python coroutines, so far I spent 2 days on the 
project. I wouldn't have bothered with that exercise if there already had been a Koa-style minimalist web 
framework in Python (supporting composition of apps and middleware), but I couldn't find one. 
Tell me if you know of one.


Requirements
---
* Python >= 3.4
* [aiohttp](https://pypi.python.org/pypi/aiohttp/) >= 0.9.2

Example apps:
---
For a simple example server see example_server_simple.py, which uses koa-logger and koa-router.
For a slightly more complex example see example_server.py: this demonstrates koa-static, koa-mount and HTTP POSTs.