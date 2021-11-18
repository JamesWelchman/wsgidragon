.. _rst_tutorial:

**********
Tutorial
**********

Running an application locally
#################################

Lets create a single file `service.py` and into that file place
the following code:

.. code-block:: python
   :linenos:

   from wsgidragon import DragonApp

   # create our application
   # we have to give it a name
   application = DragonApp("tutorial_application")

   def hello(request, _resp_head):
       """
       hello is an endpoint which will return 200 OK!
       """
       pass

    # register our endpoint
    application.add(
        hello,
	path=("hello",),
	methods=["GET"],
    )


In order to run `service.py` locally there are two options,
`gunicorn <https://gunicorn.org/>`_ and `uwsgi <https://uwsgi-docs.readthedocs.io/en/latest/>`_.

**Option 1 gunicorn**

.. code-block:: shell
		
   gunicorn -b :8000 -w1 service

**Option 2 UWSGI**

.. code-block:: shell

   uwsgi

With your service running we can now call the endpoint.

.. code-block:: shell
   :linenos:

   curl -v localhost:8000/hello
   > GET /hello HTTP/1.1
   > Host: localhost:8000
   > User-Agent: curl/7.79.1
   > Accept: */*
   > 
   * Mark bundle as not supporting multiuse
   < HTTP/1.1 200 Ok
   < Server: gunicorn
   < Date: Thu, 18 Nov 2021 03:03:22 GMT
   < Connection: close
   < X-TraceId: f188a3ce14ba2f5213f624199fb4e132
   < Content-Length: 0

We make the observation (line 12) that the server returned an *X-TraceId* header.
All requests to WSGI Dragon return an X-TraceId header. We note the logging
output produced.

.. code-block:: json

   {"service":"tutorial_application","ts":"2021-11-18T03:03:22.088332","level":"INFO","msg":"request complete","trace_id":"f188a3ce14ba2f5213f624199fb4e132","span_id":"dfd3b9e473c2a577","client":"curl/7.79.1","http.method":"GET","url.path":"/hello","url.port":8000,"url.host":"0.0.0.0","url.path.0":"hello","http.status":200}

WSGI Dragon always logs in JSON (note the *trace_id* key).

WSGI Dragon is also self-documenting so lets check our docs! http://localhost:8000/doc

Adding a JSON Response
#########################

In order to send a JSON response, lets modify two lines of our application.

.. code-block:: python
   :linenos:

   from wsgidragon import DragonApp

   # create our application
   # we have to give it a name
   application = DragonApp("tutorial_application")

   def hello(request, _resp_head):
       """
       hello is an endpoint which will return 200 OK!
       """
       return {"name": "John", "age": 42}

    # register our endpoint
    application.add_json(
        hello,
	path=("hello",),
	methods=["GET"],
    )

We see that we have modified line 11 and line 14.
Trying to call this endpoint we get:

.. code-block:: shell

   curl -v localhost:8000/hello
   > GET /hello HTTP/1.1
   > Host: localhost:8000
   > User-Agent: curl/7.79.1
   > Accept: */*
   > 
   * Mark bundle as not supporting multiuse
   < HTTP/1.1 500 Internal Server Error
   < Server: gunicorn
   < Date: Thu, 18 Nov 2021 03:17:40 GMT
   < Connection: close
   < Transfer-Encoding: chunked
   < X-TraceId: f1f84b49718ed511fa2d09166fd4656c
   < Error: body is populated, but not schema set

The server send back a 500 Internal Server Error! Why?
WSGI Dragon also provided the reason why in Error response
header. *body is populated, but schema not set*.
WSGI Dragon **forces** us to specify what the schema is.
Let's add a schema to our code.

.. code-block:: python
   :linenos:

   from wsgidragon import DragonApp, JSONSchema
   from wsgidragon import jsonschema

   # create our application
   # we have to give it a name
   application = DragonApp("tutorial_application")

   class ResponseSchema(JsonSchema):
       name = jsonschema.String(required=True)


   def hello(request, _resp_head):
       """
       hello is an endpoint which will return 200 OK!
       """
       return {"name": "John", "age": 42}

    # register our endpoint
    application.add_json(
        hello,
	response_schema=ResponseSchema,
	path=("hello",),
	methods=["GET"],
    )

We see three changes, first we import schema from wsgidragon.
We then on lines 8 and 9 we define what the schema is.
Finally on line 21 we set this as the response schema.
Let's try again:

.. code-block:: shell

   curl -v http://localhost:8000/hello
   ...
   < Error: invalid response body - [:ResponseSchema(name(required,String()))] - unrecognised key (age)


This time around the server gave us a different error.
The response body is invalid due to an unrecognised key *age*.
Lets add age to our schema and try again.


.. code-block:: python
   :linenos:

   from wsgidragon import DragonApp, JSONSchema
   from wsgidragon import jsonschema

   # create our application
   # we have to give it a name
   application = DragonApp("tutorial_application")

   class ResponseSchema(JsonSchema):
       name = jsonschema.String(required=True)
       age = jsonschema.Number(required=True)

   def hello(request, _resp_head):
       """
       hello is an endpoint which will return 200 OK!
       """
       return {"name": "John", "age": 42}

    # register our endpoint
    application.add_json(
        hello,
	response_schema=ResponseSchema,
	path=("hello",),
	methods=["GET"],
    )

Running curl again we see that 200 OK and the JSON is returned.

.. code-block:: shell

   curl -k localhost:8000/hello
   < HTTP/1.1 200 Ok
   < X-TraceId: 71a8a0b5cfd59e4f6826bd694ff4ceb2
   < Content-Type: application/json
   < Content-Length: 24
   {"name":"john","age":42}


WSGI Dragon forces us to specify a schema and sanity checks all responses.
Another upside of forcing users to specify a schema is documentation!
http://localhost:8000/doc
We see that our endpoint response schema is documented.

Returning a 201 Created Status Code
#########################################

We notice is our hello function the second argument (resp_head).
This is a function which takes two arguments, the response
status code and any custom response headers we wish to use.

.. code-block:: python

   resp_head(StatusCode.CREATED, [])

Lets add this our application

.. code-block:: python
   :linenos:

   from wsgidragon import DragonApp, JSONSchema, StatusCode
   from wsgidragon import jsonschema

   # create our application
   # we have to give it a name
   application = DragonApp("tutorial_application")

   class ResponseSchema(JsonSchema):
       name = jsonschema.String(required=True)
       age = jsonschema.Number(required=True)

   def hello(request, resp_head):
       """
       hello is an endpoint which will return some JSON
       """
       resp_head(StatusCode.CREATED, [])
       return {"name": "John", "age": 42}

    # register our endpoint
   application.add_json(
        hello,
	response_schema=ResponseSchema,
	path=("hello",),
	methods=["GET"],
   )

First we imported StatusCode from wsgidragon.
We then changed the docstring of the hello function
and added a call to resp_head. Let's try curl and
see what happened!

.. code-block:: shell

   curl -v localhost:8000/hello
   ...
   < HTTP/1.1 500 Internal Server Error
   < Error: unregistered status code

We got an Internal Server Error? WSGI Dragon helpfully provided why,
*the status code 201 is not registered*. Let's register it by changing
our register call.

.. code-block:: python

   # register our endpoint
   application.add_json(
      hello,
      response_schema=ResponseSchema,
      path=("hello",),
      methods=["GET"],
      status_codes=[StatusCode.CREATED],
   )

Running curl again we should now see that everything is working.
Furthermore our documentation (http://localhost:8000/doc) correctly
documents the status code of our endpoint.

Request Schemas, Environment Variables and URL Parameters
###########################################################

In addition to response schemas and status codes, WSGI Dragon
also sanity checks and self-documents request_schemas,
environment variables and URL Parameters. Below is a complete
example.
