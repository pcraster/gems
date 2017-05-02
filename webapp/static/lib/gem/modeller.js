var M=$.extend(M || {},{
	/*
	Default configuration values. Overwritten by those passed to M.init()
	*/
	config: {
		version:'0.1',
		api:'/api/v1/',
		debug:false
	},
	/*
	Default state variables. Will be updated as soon as a certain config
	is loaded.
	*/
	state: {
		time:undefined,
		layers:undefined,
		configkey:undefined,
		hash:undefined,
		results:undefined
	},
	criticalerror: function(message) {
		alert("Critical Error!\n\n"+message)
	},
	init: function(config) {
		/*
		First of all extent M.config with the variables passed in to
		the init() function. These will include things like the model
		name, mapserver url, and others.
		*/
		$.extend(M.config, config)

		/*
		Create the M.config["api_auth"] variable which will use the
		api_auth_username and api_auth_password config variable to
		create the HTTP Authentication header which will be sent along
		with every API call.
		*/
		M.config["api_auth"] = "Basic " + btoa(M.config["api_auth_username"] + ":" + M.config["api_auth_token"])

		/*
		Parse the hash part (after #) of the url and look for a config
		key that we can use for initializing the model. If no such key
		is found, the hash init function falls back to the valie in the
		M.config["default_config_key"] variable. The config key returned
		from M.hash.init() is later used to request the configuration
		details from the API.
		*/
		var _config_key=M.hash.init()

		/*
		Overwrite the common console methods depending on the debug
		config variable. If debug is set to false, console.log() will
		do nothing.
		*/
		if(! M.config["debug"]){
		    if(!window.console) window.console = {};
		    var methods = ["log", "debug", "warn", "info"];
		    for(var i=0;i<methods.length;i++){
		    	console[methods[i]] = function(){};
		    }
		}

		/*
		Then fetch the model configuration with the config key for
		this model run. If no key was supplied in the URL hash, the
		default key for this model will be used. After fetching the
		model configuration from the API, the "parameters" form
		will be populated with the correct input params returned by
		this call.
		*/
		M.api.config_status(_config_key)

		/*
		The server side python script added a <canvas> element for each
		output attribute which is visualized with a pseudocolor color ramp.
		Some javascript is needed though to actually fill in the colors.
		Various data attributes have been added to the canvas tag (see the
		html source) which define the color stops. This bit of code loops
		over all the canvases in the DOM and:

			- colors them in with the proper color map
			- adds tickmarks and data values to the corresponding <ul>

		*/
		M.legends.init()

		M.charts.init()

		M.chart.init()
		/*
		Initialize the graphical user interface.
		*/
		M.gui.init()
	},
	hash: {
		values:{
			configkey:'',
			zoom:9,
			geohash:'lala',
			center:[-40.3, 176.4],
			bounds:undefined,
			layers:undefined,
			time:undefined
		},
		init:function() {
			console.log("Initializing the hash: "+window.location.hash)
			var hash=window.location.hash.substring(1).split(":") //remove leading '#' and split by ':'
			if (hash[0] == "") {
				console.log("Hash is empty! Instead use the one provided as a default for this model:"+M.config.default_config_key)
				M.hash.values['configkey']=M.config.default_config_key
			}
			if (/^[a-f0-9]{32}$/.test(hash[0])) {
				console.log("Hash was found to have a config key in it: "+hash[0])
				M.hash.values['configkey']=hash[0]
			}
			if (1 in hash && 2 in hash) {
				console.log("Geohash and zoom level found in hash!")
				M.hash.values['zoom']=parseInt(hash[1])
				console.log("Found a geohash.. go there!")
				M.hash.values['geohash']=hash[2]
				var gh=decodeGeoHash(hash[2])
				M.hash.values['center']=[gh.latitude[2],gh.longitude[2]]
			} else {
				console.log("Either no geohash or no zoom found. Regardless, we don't know where to set initialize the map.")
				console.log("Therefore fall back to the bounds specified in M.config.default_view_extent")
				console.log(M.config.default_view_extent)
				var b = M.config.default_view_extent.split(",").map(parseFloat)
				M.hash.values['bounds']=[[b[1],b[0]],[b[3],b[2]]]

			}
			if (3 in hash) {
				M.hash.values['layers']=hash[3]
			}
			if (4 in hash) {
				var t=hash[4]
				//ok this is really ugly, convert a time string like "20140714000000" back
				//into one like "2014-01-15T00:00:00" which can be used in wms requests.
				M.hash.values['time']=t.substr(0,4)+"-"+t.substr(4,2)+"-"+t.substr(6,2)+"T"+t.substr(8,2)+":"+t.substr(10,2)+":"+t.substr(12,2)
			}
			console.log("returning:")
			console.log(M.hash.values)
			return M.hash.values['configkey']
		},
		update:function(options) {
			var _map_location=$.extend(true,M.map.obj.getCenter(),{zoom:M.map.obj.getZoom()})
			var _hash=[]
			var geohash=encodeGeoHash(_map_location["lat"],_map_location["lng"])
			var dgeo=decodeGeoHash(geohash)

			_hash.push(M.state["configkey"])
			_hash.push(_map_location["zoom"])
			_hash.push(geohash)
			_hash.push(M.state["layers"])
			_hash.push(M.state["time"].replace(/\D/g,''))
			M.hash.set(_hash.join(":"))
		},
		set:function(hash) {
			history.replaceState(undefined, undefined, "#"+hash)
		}
	},
	menu: {
		waiting:function() {
			$('div#waiting').show();
			$('li#finished').hide();
		},
		finished:function() {
			$('div#waiting').hide();
			$('li#finished').show();
		},
		run:{
			init:function(){
				M.menu.run.el=$('a#menu-run')
				M.menu.run.el.on('click',M.menu.run.click)
				M.menu.run.el.tooltip(M.defaults.tooltip(''));
				M.menu.run.disable('test')
				M.menu.run.enable()
				M.menu.finished()
			},
			tooltip:function(message) {
				M.menu.run.el.data('bs.tooltip').options.title=message
			},
			disable:function(message) {
				M.menu.run.is_disabled=true
				M.menu.run.el.addClass("disabled")
				M.menu.run.tooltip(message)
			},
			enable:function(message) {
				M.menu.run.el.removeClass("disabled")
				M.menu.run.tooltip('Run the model with the selected configuration<br/><span style="color:#666;"><nobr> Ctrl&ndash;Enter</nobr></span>');
			},
			click:function(evt) {
				evt.preventDefault();
				M.menu.run.el.blur()
				if(M.menu.run.el.hasClass("disabled")) {
					console.log("Your clicking is futile.")
				} else {
					M.api.job_create()
				}
			}
		}
	},
	map: {
		init:function(data) {
			/*
			Initialize the leaflet map object. It is stored in M.map.obj.
			*/
			M.map.obj = L.map('map',{
				'layers':MQ.mapLayer(),
				'scrollWheelZoom':true,
				'zoomControl':false,
				'minZoom':4,
				'maxZoom':20,
				/*
				'attributionControl':false,*/
			});

			M.map.geojsonlayer = L.geoJson(undefined, {
				'style':{
					"color": "#e50000",
					"weight": 2,
					"opacity": 1.0,
					"fillOpacity": 0
				},
				onEachFeature: function(feature, layer) {
					layer.on('click', function(e) {
						M.map.obj.fitBounds(layer.getBounds(),{'padding':[20,20]})
					})
				}
			}).addTo(M.map.obj);

			L.control.zoom({position:'bottomright'}).addTo(M.map.obj);
			L.control.scale({position:'bottomleft'}).addTo(M.map.obj);
			/*
			Attache some events for when the map is moving
			*/
			M.map.obj.on('movestart',M.map.movestart)
			M.map.obj.on('moveend',M.map.moveend)
			M.map.obj.on('load',M.map.updateSize)
			M.map.obj.on('click',M.map.pointInfo)

			console.log("setting view to hash center and zoom:")
			console.log(M.hash.values)
			if (M.hash.values['bounds'] != undefined) {
				console.log("Fitting to bounds:")
				M.map.obj.fitBounds(M.hash.values['bounds'])
			} else {
				M.map.obj.setView(M.hash.values['center'], M.hash.values['zoom']);
			}

			var LeafIcon = L.icon({
			        iconUrl: '/static/lib/gem/target_icon_border.png',
			        iconSize:     [33, 33],
			        iconAnchor:   [16, 16]
			});

			//M.map.obj.on('mousemove',$.debounce(M.map.pointInfo,250));
			M.map.marker = L.marker([51.5, -0.09],{icon:LeafIcon}).addTo(M.map.obj);

			/*
			Bind a resize event to the window which resizes the div which
			contains the map. This div needs to have an absolute size.
			*/
			$(window).on("resize",$.debounce(M.map.updateSize,250));
			//$(window).resize(M.map.updateSize);
		},
		bbox: function() {
			return M.map.obj.getBounds().toBBoxString()
		},
		datalayer: undefined,
		geojsonlayer: undefined,
		moveend:function(){
			/*
			Triggered on a leaflet moveend event. Call the api
			and get info back on the extent. Enable the run button
			if the extend isnt too large
			*/
			M.api.job_prognosis()
			M.map.updatestate()
			M.gui.done('map-moving')
		},
		updatestate:function(){
			console.log("updatestate()")

			if(M.map.datalayer != undefined && M.state["results"]!=undefined) {
				M.state['layers'] = M.map.datalayer.wmsParams.layers
				M.state['time'] = M.map.datalayer.wmsParams.time
				M.state['configkey'] = M.map.datalayer.wmsParams.configkey

				$('select#selected-timestamp option').each(function(index,option){
					var option=$(this)
					var selected=(option.val()==M.state['time'])?"selected":"";
					option.prop("selected",selected)
					var disabled=M.state["results"].timesteps[index]["attributes"].hasOwnProperty(M.state['layers'])?false:true;
					option.prop("disabled",disabled)
				})
				var timestepIndex=$('select#selected-timestamp')[0].selectedIndex;

				if (timestepIndex == -1) {
					alert('trying to update the attribute list, but no timestep is selected!')
				}
				console.log("Looking for timestep ix:"+timestepIndex)
				$('form#attribute-form input[type=radio][name=selected-attribute]').each(function(){
					var radio=$(this)
					var checked=(radio.val()==M.state['layers'])?"checked":""
					var disabled=M.state["results"].timesteps[timestepIndex]["attributes"].hasOwnProperty(radio.val())?false:true;
					radio.prop("checked",checked)
					radio.prop("disabled",disabled)
					radio.parent().prop("class",disabled?"disabled":"") //possibly set the <label>'s class to disabled
				})

				/*
				Maybe update the rest of the UI (chart, legend) also here instead of in the
				setAttribute command...
				*/

				M.hash.update()
			}
		},
		movestart:function(){
			M.gui.busy('map-moving')
		},
		pointInfo:function(e) {
			M.map.marker.setLatLng(e.latlng);
			M.charts.get('timeseries').update({
				'lat':e.latlng.lat,
				'lng':e.latlng.lng,
				'layers':M.state.layers,
				'configkey':M.state.configkey,
				'time':M.state.time
			})
		},
		update:function(params){
			/*
				Update function updates the map's data layer. The first time update
				is called (when M.map.datalayer is still undefined) the datalayer
				is created. Subsequent calls use the data layer setParams() method
				to update the parameters.
			*/
			if(M.map.datalayer==undefined) {
				if('layers' in params && 'time' in params && 'configkey' in params && 'map' in params && 'mapserver' in params) {
					console.log("Initial loading of the data map layer!")
					var dataLayer=L.tileLayer.wms(params["mapserver"], {
						layers:params['layers'],
						time:params['time'],
						map:params['map'],
						format: 'png8',
						tileSize: 512,
						transparent: true,
						//attribution: "FG-VG",
						subdomains: '1234',
						configkey:params['configkey'],
						random:Math.random()
					})
					dataLayer.on('loading',function(){
						console.log("Start loading data")
						M.gui.busy('map-loading')
					});
					dataLayer.on('load',function(){
						console.log("End loading data")
						M.gui.done('map-loading')
					});
					M.map.datalayer=dataLayer
					M.map.datalayer.addTo(M.map.obj);

					/*
					Initializes the attributes panel of the map which shows
					a list of attributes, timesteps, and a colormap legend.
					*/
					var control=L.control({'position':'topright'})
					control.onAdd=function (map) {
						var div = L.DomUtil.get('panel-attributes');
						if (!L.Browser.touch) {
						    L.DomEvent.disableClickPropagation(div);
						    L.DomEvent.on(div, 'mousewheel', L.DomEvent.stopPropagation);
						} else {
						    L.DomEvent.on(div, 'click', L.DomEvent.stopPropagation);
						}
						return div;
					}
					control.addTo(M.map.obj)

					/*
					Attach events to the attribute radio buttons and the select
					box to change the 'layers' and 'time' params of the wms tile
					layer
					*/
					$('input[type=radio][name=selected-attribute]').change(function() {
						$(this).blur()
						M.map.setAttribute(this.value)
					});
					$('select#selected-timestamp').change(function(){
						M.map.setTime(this.value)
					})

					M.map.setTime(params['time'])
					M.map.setAttribute(params['layers'])

				} else {
					/* datalayer is undefined, but you're not passing the required info
					   to be able to initialize it... */
					alert("not enough data to initialize data layer")
					return false
				}
			} else {
				console.log("Datalayer is defined, so we can update it with the passed info:")
				console.log(params)
				M.map.datalayer.setParams(params, true)
				M.map.datalayer.redraw()
			}
			M.map.updatestate()
		},
		setAttribute:function(attribute) {
			console.log("setAttribute: "+attribute)
			M.map.update({layers:attribute})

			M.legends.show(attribute)
			M.charts.get('timeseries').update({'layers':attribute})
		},
		setTime:function(time) {
			console.log("setTime: "+time)
			/* check if this time is even available in the result set */
			$("p#panel-timesteps-label").html("Attribute map at UTC time "+time)
			M.map.update({time:time})
			M.charts.get('timeseries').setTime(time)
		},
		updateSize:function() {
			/*
			Updates the map size to match the space from the bottom of the navbar to the
			bottom of the document.
			*/
			var windowHeight=$(window).height();
			var navbarHeight=$("body nav").height();
			var navbarOffset=$("body nav").offset();
			$('div#map').height(windowHeight-navbarHeight-navbarOffset.top)
			M.map.obj.invalidateSize()
		},
		// fetchresults:function(job_id) {
		// 	alert("fetchresults")
		// 	$.ajax({
		// 		type:"GET",
		// 		url:"/api/v1/job/"+job_id,
		// 		success: function(data) {
		// 			if ( (data["status_code"]==1) && (data["results"]) ) {
		// 				M.map.processresults(data.results)
		// 			} else {
		// 				alert("Eh.. job not done?")
		// 			}
		// 		},
		// 		error: function(){
		// 			console.log("Error fetching status!")
		// 		}
		// 	})
		// },
		processresults:function(results) {
			console.log("processresults()")
			M.state['results'] = results

			/* get the currently selected index */
			var timestepIndex=$('select#selected-timestamp')[0].selectedIndex;

			var numOfTimesteps = M.state['results']['timesteps'].length
			if(numOfTimesteps > 0) {
				/*
				What timestep should be selected after filling the <select> box with timestamps?
				*/
				var timestepSelectBox = $('select#selected-timestamp')
				var preferredTime = timestepSelectBox.val()

				/*
				We got some results back after a model run, and it contains a number of time-
				steps that need to be processed. First order of business is to loop through
				the timesteps and add them all to the timesteps select box in the interface.
				Usually this will not be necessary as the timesteps of a model with a static
				starting time will not change, but for forecast models it may be that the
				start time has changed in the meantime, and we need to load new times into the
				select box with timesteps.

				*/
				var selectableTimesteps=[]
				timestepSelectBox.html("")
				$.each(M.state['results']['timesteps'],function(index,timestep){
					timestepSelectBox.append('<option value="'+timestep.timestamp+'">'+index+'. '+timestep.timestamp+'</option>')

					if (M.state['layers'] in timestep.attributes) {
						selectableTimesteps.push(timestep.timestamp)
					}
				})

				if ( $.inArray(preferredTime,selectableTimesteps) != -1) {
					preferredTime=preferredTime
				} else {
					preferredTime=selectableTimesteps[selectableTimesteps.length-1]
				}

				M.state['time']=preferredTime

				/*
				This function processes incoming result data to update the map accordingly.
				Sometimes the map doesn't have a current state yet (ie. a selected attribute
				and timestep), like when the model has just been edited and no runs have been
				done yet with this new configuration. In that case we need to select some
				sensible defaults to show to the user. So, here we check if the state 'time'
				and 'layers' variables are undefined, and assign some sensible defaults
				if they are.
				*/

				var defaultTime=(M.hash.values["time"]==undefined)?results['timesteps'][numOfTimesteps-1]['timestamp']:M.hash.values["time"];
				var defaultLayers=(M.hash.values["layers"]==undefined)?Object.keys(results['timesteps'][numOfTimesteps-1]['attributes'])[0]:M.hash.values["layers"];

				if(numOfTimesteps == 1) {
					/*
					Lets not muck about with a timesteps select box if there is only one
					timestep to choose from.
					*/
					$("div#panel-timesteps").hide()
				}

				/*
				Only when loading in new results, for example after a model run, we set a
				new random number. This will *force* the map tiles to do a hard reload from
				the server. The random parameter is ignored in the server caching mechanisms.
				*/
				var newRandomValue = Math.random()

				M.map.update({
					configkey:results['config_key'],
					mapserver:M.config["mapserver"],
					map:M.config['mapfile'],
					layers:(M.state['layers']==undefined)?defaultLayers:M.state['layers'],
					time:(M.state['time']==undefined)?defaultTime:M.state['time'],
					random:newRandomValue
				})


			} else {
				/*
				So we had some results come in, but these results contained no data on time-
				steps. This usually happens after a model has just been edited. When the user
				visits the modeller, the default configuration for that model is loaded into
				the map. However, there are no results yet created with this config key, so
				we simply do nothing.
				In other scenarios when there is a deeplink to a particular model configuration,
				some timesteps actually exist in the database and the timesteps will be loaded
				as normal.
				*/
				console.log("These results have no timesteps. wat to do?")
			}
			return true
		}
	},
	chart: {
		defaultOptions:{
			color: "rgb(255,50,50)",
			series: {
				lines: {
					show: true,
					color: "rgb(255,50,50)",
					fill: true,
					fillColor: '#FFCCCC'
				},
				color: "rgb(255,50,50)",
				points: { show: true }
			},
			shadowSize:0,
			grid: {
				hoverable: true,
				clickable: true,
				borderWidth: 0,
				markings: [
					{ xaxis: { from: 7.5, to: 8.5 },color: "yellow" } /*,
					{
						yaxis: {from: 1.0, to: 1.5},
						xaxis: {from: 5.0, to: 6.5},
						color: "yellow"
					}*/
				]
			},
			yaxes: [
					{
						min: 0.0,
						max: 1.5,
						ticks: 4
					}
				],
			xaxes: [
	                {
	                	position:'bottom',
	                	ticks:10,
	                	min:-0.5,
	                	max:12.5
	                },
	                {
						mode: "time",
						//min: (new Date(1996, 0, 1)).getTime(),
						//max: (new Date(2000, 0, 1)).getTime(),
						//minTickSize: [2, "month"]
					}

	                /*,{
	                	mode: "time", min:(this.modelepoch-(this.data.time.timeunitlength*1000*0.5)), max:(this.modelepoch+((this.data.time.timesteps-1)*this.data.time.timeunitlength*1000)+(this.data.time.timeunitlength*1000*0.5))
	                } */
            ]
		},
		show:function(){
			console.log("showtimeseries")
			$("div#legend-chart-timeseries").show()
		},
		hide:function() {
			console.log('hidetimeseries')
			$("div#legend-chart-timeseries").hide()
		},
		update:function(data) {
			/*
			Update the timeseries chart with new data.
			*/
			var chartOptions = data.hasOwnProperty("yaxis") ? $.extend({}, M.chart.defaultOptions, {'yaxes':[data['yaxis']]}):M.chart.defaultOptions;
			var numValues = data.hasOwnProperty("value") ? data["value"].length : 0
			var numTimestamps = data.hasOwnProperty("timestamp") ? data["timestamp"].length : 0

			if( (numValues == numTimestamps) && (numValues > 1) && (numTimestamps > 1) ) {
				console.log("Looks like we have some plottable data, show timeseries chart and update it.")
				var series = []
				for (var n = 0; n < data["value"].length; n+=1) {
					series.push([Date.parse(data["timestamp"][n]),data["value"][n]])
				}
				var chartData = [
					{ data: series, color: 'rgba(255,0,0,0.0)',  xaxis: 1 },
					{ data: series, xaxis: 2 }
				]
				M.chart.show()
				$.plot("#legend-chart-timeseries-placeholder", chartData, chartOptions);
			} else {
				M.chart.hide()
				console.log("Hmm no point in plotting this really...")
			}

		},
		init:function() {
			/*
			Set the width to the same width as the panel div, this is because the
			chart container needs to have a fixed size for the chart to be rendered
			propertly.
			*/
			var chartWidth = $('div#panel-legend').width()
			var chartAspectRatio = 0.6

			$('div.legend-chart-placeholder').width(chartWidth)
			$('div.legend-chart-placeholder').height(chartWidth * chartAspectRatio)

			//M.chart.hide()
		}
	},
	panels: {
		init:function(parameters) {
			/*
			Set the click event on the 'edit parameters' link in the menu which
			shows/hides the form with input params.
			*/
			$('a#menu-editparameters').click(function(evt){
				//evt.preventDefault()
				//$('#panel-params').toggle()
				$(this).blur()
				M.panels.editparams()

			})
			$('a#menu-findplaces').click(function(){
				$(this).blur()
				M.panels.findplaces()
			})

			/*
			Set the values in the form with input parameters that correspond
			with the configuration key. The form will have default values of
			'###' for all parameters, and these need to be updated to reflect
			the correct values.
			*/
			$.each(parameters, function(key,value){
				$("form#model-parameters input#"+key).val(value)
			})

			/*
			Now that the form contains the right values, we need to attach some
			events to the inputs which trigger a new prognosis API request when
			the value changes. For example, when you change a parameter from
			0.1 to 0.5, we need to call the server to get a new configuration
			key, and to see how many chunks need to be run if we're going to
			use the new key.
			*/
			$("form#model-parameters input").on("change",function(){
				var input=$(this)
				//console.log("Input "+input.prop("id")+" has changed!!")
				M.api.job_prognosis()
				M.map.updatestate()
			})
			/*
			We add a control to the layer select tab that slides in the layers.
			This way the chart does not get hidden on smaller screens.
			*/
			$("h2#output-layer-header").on("click",function(){
				$("form#attribute-form").slideToggle()
				$("div#arrow").toggleClass("arrow-down arrow-right")
			})
			/*
			Add the control with input params to the top left of the Leaflet map
			and disable that mousewheel and click events propagate to the map
			layer itself.
			*/
			var control=L.control({'position':'topleft'})
			control.onAdd=function (map) {
				var div = L.DomUtil.get('panel');
				if (!L.Browser.touch) {
				    L.DomEvent.disableClickPropagation(div);
				    L.DomEvent.on(div, 'mousewheel', L.DomEvent.stopPropagation);
				} else {
				    L.DomEvent.on(div, 'click', L.DomEvent.stopPropagation);
				}
				return div;
			}
			control.addTo(M.map.obj)

			/*
			Once the control has been added to the map and it contains proper
			values, fire off a prognosis API call to see whether the model can
			be run given the current map location.
			*/
			M.api.job_prognosis()
		},
		findplaces:function(){
			M.panels.toggle("panel-findplaces")
			$('form#find-places input[name=q]').focus()
		},
		editparams:function() {
			M.panels.toggle("panel-params")
		},
		notifications:function() {
			//eh
		},
		showonly:function(id) {
			$("div#panel div.map-panel").each(function(){
				var panel=$(this)
				if(this.id==id) {
					panel.show()
				} else {
					panel.hide()
				}
			})
		},
		toggle:function(id) {
			$("div#panel div.map-panel").each(function(){
				var panel=$(this)
				if(this.id==id) {
					panel.toggle()
				} else {
					panel.hide()
				}
			})

		}
	},
	params: {
		serialize:function(){
			/*
			Serializes the form parameters and adds a parameter 'bbox' which defines
			the extent of the requested model run. This data is then sent off as a
			prognosis API request.
			*/
			var formdata=$("form#model-parameters").serializeArray()
			formdata.push({'name':'bbox','value':M.map.bbox()})
			return formdata
		}
	},
	places: {
		init:function() {
			/*
			Initialize the 'find places' functionality.

			Todo: Add some sort of keypress events for down and up which select/focus
			to the next or previous link in the list of places in the search results.
			This would let users type and then use the down arrow and enter to select
			the right result.
			*/
			$("form#find-places").on("submit",function(evt){
				evt.preventDefault()
				return false
			})
			$('form#find-places input[name=q]').keyup($.debounce(function() {
				var form=$("form#find-places")
				if ($('form#find-places input[name=q]').val()!="") {
					$.ajax({
						url: form.prop("action"),
						dataType: "json",
						data: form.serializeArray(),
						success: function(data) {
							var res=$('div#results-list').html("");
							for(var i in data.geonames) {
								var result=data.geonames[i];
								var a=$('<a href="#" data-lat="'+result.lat+'" data-lng="'+result.lng+'" style="padding:5px 10px;idth:100%px;white-space:nowrap;overflow:hidden;text-overflow: ellipsis;" class="list-group-item">'+result.name+' ('+result.countryName+')</a>')
								a.click(function(evt){
									var a=$(this).blur()
									M.map.obj.panTo(L.latLng(parseFloat(a.data("lat")), parseFloat(a.data("lng"))))
									evt.preventDefault()
									$('div#panel-findplaces').hide()
								})
								res.append(a)
							}
						}
					});
				}
			},250));
		}
	},
	defaults:{
		tooltip:function(message){
			return {
				html:true,
				placement:'auto',
				title:message,
				trigger:'hover focus',
				viewport:{ selector: 'body', padding: 7 }
			}
		}
	}
});

