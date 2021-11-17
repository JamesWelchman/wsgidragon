<h3> Default Status Codes </h3>
All WSGI Dragon applications can return the following status codes.
<li>400 Bad Request</li>
<li>404 Not Found</li>
<li>500 Internal Server Error</li>
<li>504 Gateway Timeout</li>

<p>Individual routes define additional status codes
which they return.<p>

<h3>Environment Variables</h3>
% for key in sorted(environ):
    <li>${key}=${environ[key]}
    <div class="envvar-desc">
    <p>${environ.description(key)}</p>
    </div>
    </li>
% endfor
