<h2>${route.api.name}</h2>
<div class="route-path">
${"/".join(route.api.path)}
</div>

<div class="handler-docstring">
${route.clb.__doc__}
</div>

<h3>Methods</h3>
% for m in route.methods:
  <li>${m}</li>
% endfor

<h3>Status Codes</h3>
% for s in route.api.status_codes:
  <li>${s.value[0]} ${s.value[1]}</li>
% endfor

<div class="schema-html">
${route.api.schema_html(route.path)}
</div>