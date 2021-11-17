<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="utf-8">
    <title>
        % if routes:
	    ${routes[0].api.service_name}
	% else:
	    Documentation
	% endif
    </title>
    <link rel="stylesheet" href="doc/style.css">
  </head>
	<body>

		<div id="containers">

		     <div id="heading">
		     		<h1 class="pageHeader">
				% if routes:
				    ${routes[0].api.service_name}
				% else:
				    Documentation
				% endif
				</h1>
		     </div>

	<div id="content">

	     <div id="sidebar">
	     	  <div id="routes-header">
	          <h3> routes </h3>
		  </div>
		  % for route in routes:
		    <li id=${route.api.id}>${route.api.name}</li>
		  % endfor
	     </div>

	  <div id="main-content">
	  </div>

	  <!-- end of content -->
	</div>

	<div id="footer">
	     <p>footer</p>
	</div>

		<!-- end of containers -->
		</div>
	</body>

<script type="application/javascript">
        const mainContent = document.getElementById("main-content");

	function _setMainContent(request) {
            fetch(request)
	        .then(response => response.text())
		.then(text => {
			   mainContent.innerHTML = text;
		});
	}

	function setMainContent(route) {
		 const request = new Request("doc/route?route=" + route);
		 _setMainContent(request);
	}

        function setMainContentMain() {
		 const request = new Request("doc/main.html");
		 _setMainContent(request);
	}

	% for route in routes:
	    const route${route.api.id} = document.getElementById("${route.api.id}");
	    route${route.api.id}.addEventListener('click', (_e) => {
	        setMainContent("${route.api.id}");
	    });
	% endfor

	// Load the main page when routes if clicked
	document.getElementById("routes-header").addEventListener('click', (_e) => {
					      setMainContentMain();
	});
	document.getElementById("heading").addEventListener('click', (_e) => {
		setMainContentMain();
	});

	window.onload = function() {
		      setMainContentMain();
	};
</script>
</html>