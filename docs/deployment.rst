Deployment
==========

How the live instance at https://touchpath.onrender.com is deployed, and three other ways to do it.

The application is a standard ASGI app, so anything that runs FastAPI runs this.

--------------

How the live instance is deployed
---------------------------------

**Render, via a blueprint.** The repository contains ``render.yaml``:

.. code:: yaml

   services:
     - type: web
       name: touchpath
       runtime: python
       plan: free
       buildCommand: pip install -e ".[web]"
       startCommand: uvicorn touchpath.web.app:app --host 0.0.0.0 --port $PORT
       healthCheckPath: /healthz
       envVars:
         - key: PYTHON_VERSION
           value: "3.12"

The steps, start to finish:

1. Sign in to Render with GitHub and authorise access to the repository.
2. **New → Blueprint**, select ``touchpath``, apply. Render reads ``render.yaml`` and configures the build, start command, health check and Python version itself.
3. The first build takes under a minute: clone, ``pip install -e ".[web]"``, start uvicorn, wait for ``/healthz`` to return 200.
4. Every subsequent ``git push`` to ``main`` redeploys automatically.


.. admonition:: The free tier sleeps
   :class: warning

   A free Render instance spins down after about 15 minutes of inactivity, and the next request takes up to a minute to wake it. For a demo that people will click on without warning, either accept it and say so on the page, or keep it warm with an external uptime pinger hitting ``/healthz`` every ten minutes.


--------------

Docker
------

The repository includes a ``Dockerfile``:

.. code:: bash

   docker build -t touchpath .
   docker run -p 8000:8000 touchpath

It is a plain ``python:3.12-slim`` base, so it builds on both amd64 and arm64.

--------------

A server you control
--------------------

Full step-by-step instructions for a free Oracle Cloud instance with a real hostname and automatic HTTPS are in `DEPLOY.md <https://github.com/bhushanladde02/touchpath/blob/main/DEPLOY.md>`__ in the repository. The outline:

1. Create a ``VM.Standard.E2.1.Micro`` instance (Always Free, 1 GB RAM — enough, since the service idles under 200 MB).
2. Install, create a virtualenv, ``pip install -e ".[web]"``.
3. Run under systemd with ``Restart=always`` and a ``MemoryMax`` ceiling.
4. **Open the firewall in both layers** — the cloud security list *and* the instance’s own iptables. Opening one does nothing on its own, and this is where most of the debugging time goes.
5. Point a hostname at the public IP.
6. Put Caddy in front as a reverse proxy; it obtains and renews the certificate itself.

The application binds to ``127.0.0.1`` in that setup and is reachable only through the proxy.

--------------

Any other platform
------------------

The start command is the only thing that matters:

.. code:: bash

   uvicorn touchpath.web.app:app --host 0.0.0.0 --port $PORT

A ``Procfile`` is included for Railway, Fly and Heroku-style platforms.

--------------

Operational notes
-----------------

**No state.** No database, no disk writes, no sessions. Scaling is adding instances; there is nothing to coordinate.

**Memory.** About 170 MB with all five sample datasets cached — 84 MB of data plus the Python and FastAPI baseline. The samples are generated on demand and memoised, so the first request for each one costs about a third of a second.

**Health check.** ``GET /healthz``. Use it for both the platform’s probe and any uptime monitor.

**Upload limit.** 25 MB, enforced in the application. Raise ``MAX_UPLOAD_BYTES`` in ``web/app.py`` if you need more, and check your proxy’s limit too.

**Logs.** Uvicorn’s access log goes to stdout. No application logging of request bodies, deliberately — uploaded data is never written anywhere.

**Updating a server deployment:**

.. code:: bash

   cd ~/touchpath
   git pull
   .venv/bin/pip install -e ".[web]"
   sudo systemctl restart touchpath

--------------

Troubleshooting
---------------

+----------------------------------------------------+-------------------------------------------------------------------------------+
| Symptom                                            | Cause                                                                         |
+====================================================+===============================================================================+
| Blueprint created the service but nothing deployed | Trigger the first build manually: **Manual Deploy → Deploy latest commit**    |
+----------------------------------------------------+-------------------------------------------------------------------------------+
| Wake screen never resolves                         | There is no deploy yet, or the health check is failing — check the deploy log |
+----------------------------------------------------+-------------------------------------------------------------------------------+
| ``localhost:8000/healthz`` fails locally           | App not running; check ``journalctl -u touchpath -n 50``                      |
+----------------------------------------------------+-------------------------------------------------------------------------------+
| Unreachable externally, fine locally               | Firewall. Both layers.                                                        |
+----------------------------------------------------+-------------------------------------------------------------------------------+
| Certificate issuance fails                         | Port 80 blocked, or DNS has not propagated yet                                |
+----------------------------------------------------+-------------------------------------------------------------------------------+
| Service restarting repeatedly                      | Memory ceiling too low, or the start command is wrong                         |
+----------------------------------------------------+-------------------------------------------------------------------------------+
