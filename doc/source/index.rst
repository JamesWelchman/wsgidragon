WSGIDragon
======================================

WSGIDragon is Python WSGI framework.
If it's your first time here, there is a :ref:`rst_tutorial`.

Source code is maintained on `github <https://github.com/jameswelchman/wsgidragon>`_.

Features:
   * `Traceparent headers <https://www.w3.org/TR/trace-context-1/>`_
   * Parallel HTTP Call API
   * JSON and URL param sanity check **enforced**
   * JSON logging to stdout
   * All routes **self-document** schemas, params and status codes

.. code-block :: python

   from wsgidragon import DragonApp

   # create our application
   # we have to give it a name
   application = DragonApp("tutorial_application")

   def hello(request, resp_head):
       """
       hello is a handler which will return 200 OK
       """

    # register our endpoint
    application.add(
        hello,
	path=("hello",),
	methods=["GET"],
    )
    

.. toctree::
   tutorial
   headers
   path
   jsonschema
   urlparams
   environment
   caller



Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`
