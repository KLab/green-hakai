Writing Scenario
================

Actions
-------

Action represents one request and following redirects.

`path` is an only required parameter for action.

`method` is one of `GET` (default) or `POST`.
When `method` is `POST`, `post_params` can be specified and sent
as a form data.

.. code-block:: yaml

    actions:

      # GET request
      - path: /hello?spam=egg

      # POST request
      - path: /hello
        method: POST
        post_params:
          spam: egg

Variables
----------

TODO