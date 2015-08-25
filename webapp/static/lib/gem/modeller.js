var M=$.extend(M || {},{
	config: {
		version:'0.1',
		api:'/api/v1'
	},
	state: {
		time:undefined,
		layers:undefined,
		configkey:undefined,
		hash:undefined,
		results:undefined
	},
	init: function(config) {
		/*
		First of all extent M.config with the variables passed in to
		the init() function. These will include things like the model
		name, mapserver url, and others.
		*/
		$.extend(M.config,config)
		var _config_key=M.hash.init()

		/*
		Then fetch the model configuration with the config key for
		this model run. If no key was supplied in the URL hash, the 
		default key for this model will be used. After fetching the
		model configuration from the API, the "parameters" form 
		will be populated with the correct input params.
		*/
		$.ajax({
			type:"GET",
			url:"/api/v1/config/"+_config_key,
			dataType:'json',
			success: function(data) {
				console.log("Retrieved configuration data for config '"+_config_key.substr(0,6)+"':")
				console.log(data)
				M.state["results"]=data.results
				M.state["parameters"]=data.parameters
				M.state["timesteps"]=data.timesteps

				M.menu.run.init()
				M.map.init()

				M.map.processresults(M.state["results"])

				M.panels.init(M.state["parameters"])
				M.places.init()
			},
			error: function(){
				alert("An unexpected error occurred while fetching the configuration! Without a model configuration there isn't much we can do!")
			}
		});

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
		Initialize the keybinding we want to use.
		*/
		M.gui.keybindings()
	},
	gui:{
		busy:function(key) {
			if(M.gui.list.indexOf(key)==-1) {
				M.gui.list.push(key)
			}
			M.gui.disable("")
		},
		done:function(key) {
			var index=M.gui.list.indexOf(key)
			if(index!=-1) {
				M.gui.list.splice(index,1)
			}
			if(M.gui.list.length==0) {
				/*
				Good news, the gui is no longer 'busy' doing stuff. This
				means we can enable stuff again.
				*/
				M.gui.enable()
			}
		},
		enable:function() {
			/* 
			We are enabling the gui, but the run button may only be active
			when the last prognosis request yielded a positive result. 
			*/
			if(M.state['prognosis']==true) {
				M.menu.run.enable()
			} else {
				M.menu.run.disable(M.state['prognosis_message'])
			}
		},
		disable:function(message) {
			M.menu.run.disable(message)
		},
		notification:function(notification) {
			$('p#notification-message').html(notification)
		},
		keybindings:function() {
			$(window).bind('keydown', function(event) {
				if (event.ctrlKey || event.metaKey) {
					switch (event.which) {
						case 70:
							event.preventDefault();
							M.panels.findplaces();
							break;
						case 69:
							event.preventDefault();
							M.panels.editparams();
							break;
						case 13:
							event.preventDefault();
							alert("Call the run function!")
					}
				}
				if (event.which == 32) {
					if (M.map.datalayer != undefined) {
						M.map.datalayer.setOpacity(0.0)
					}
				}
			});
			$(window).bind('keyup', function(event) {
				if (event.which == 32) {
					if (M.map.datalayer != undefined) {
						M.map.datalayer.setOpacity(1.0)
					}
					//event.preventDefault();
				}
			});
		},
		thinking:false,
		list:[]
	},
	hash: {
		values:{
			configkey:'',
			zoom:9,
			geohash:'rch2v30yzbzc',
			center:[-40.3, 176.4],
			layers:undefined,
			time:undefined
		},
		init:function() {
			console.log("initializing hash: "+window.location.hash)
			var hash=window.location.hash.substring(1).split(":") //remove leading '#' and split by ':'
			if (hash[0] == "") {
				console.log("Hash is empty! Instead use the one provided as a default for this model:"+M.config.default_config_key)
				M.hash.values['configkey']=M.config.default_config_key
			}
			if (/^[a-f0-9]{32}$/.test(hash[0])) {
				console.log("Hash was found to have a config key in it: "+hash[0])
				M.hash.values['configkey']=hash[0]
			}
			if (1 in hash) {
				M.hash.values['zoom']=parseInt(hash[1])
			}
			if (2 in hash) {
				console.log("Found a geohash.. go there!")
				M.hash.values['geohash']=hash[2]
				var gh=decodeGeoHash(hash[2])
				M.hash.values['center']=[gh.latitude[2],gh.longitude[2]]
			} else {
				console.log("no geohash found..")

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
					M.api.run()
				}
			}
		}
	},
	map: {
		obj:{}, //M.map.obj will hold the Leaflet map object
		marker:{},
		bbox: function() {
			return M.map.obj.getBounds().toBBoxString()
		},
		datalayer: undefined,
		geojsonlayer: undefined,
		init:function(data) {
			/*
			Initialize the leaflet map object.
			*/
			M.map.obj=L.map('map',{
				'scrollWheelZoom':true,
				'zoomControl':false,
				'minZoom':4,
				'maxZoom':20,
				'attributionControl':false,
			});
			/*
			Add the background tile layer to the map.
			*/
			L.tileLayer('http://otile{s}.mqcdn.com/tiles/1.0.0/map/{z}/{x}/{y}.jpg', {
				attribution: '',
				maxZoom: 18,
				subdomains: '1234'
			}).addTo(M.map.obj);

			M.map.geojsonlayer = L.geoJson(undefined, {
				'style':{
					"color": "#e50000",
					"weight": 2,
					"opacity": 1.0,
					"fillOpacity": 0
				}
			}).addTo(M.map.obj);



			L.control.scale({position:'bottomleft'}).addTo(M.map.obj);
			/*
			Attache some events for when the map is moving
			*/
			M.map.obj.on('movestart',M.map.movestart)
			M.map.obj.on('moveend',M.map.moveend)
			M.map.obj.on('load',M.map.updateSize)
			M.map.obj.on('click',M.map.pointInfo)
			M.map.obj.setView(M.hash.values['center'], M.hash.values['zoom']);


			var LeafIcon = L.icon({
			        iconUrl: '/static/lib/gem/target_icon_border.png',
			        iconSize:     [33, 33],
			        //shadowSize:   [50, 64],
			        iconAnchor:   [16, 16]
			        //shadowAnchor: [4, 62],
			        //popupAnchor:  [-3, -76]
			    
			});

			//M.map.obj.on('mousemove',$.debounce(M.map.pointInfo,250));
			M.map.marker = L.marker([51.5, -0.09],{icon:LeafIcon}).addTo(M.map.obj);


			// var grid = L.grid({
			// 	redraw: 'moveend',
			// 	coordStyle: 'MinDec',
			// 	lineStyle: {
			// 		stroke: true,
			// 		color: '#111',
			// 		opacity: 0.4,
			// 		weight: 0.6
			// 	}
			// }).addTo(M.map.obj);
			/*
			Bind a resize event to the window which resizes the div which
			contains the map. This div needs to have an absolute size.
			*/
			$(window).on("resize",$.debounce(M.map.updateSize,250));
			//$(window).resize(M.map.updateSize);
		},
		moveend:function(){
			/*
			Triggered on a leaflet moveend event. Call the api
			and get info back on the extent. Enable the run button
			if the extend isnt too large
			*/
			M.api.prognosis()
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
						configkey:params['configkey']
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
				M.map.datalayer.setParams(params)
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
			Fixes the map size relative to other elements in the page. Call this when the 
			window or map size changes.
			*/
			var windowHeight=$(window).height();
			var navbarHeight=$("body nav").height();
			$('div#map').height(windowHeight-navbarHeight)
			M.map.obj.invalidateSize()
		},
		fetchresults:function(job_id) {
			$.ajax({
				type:"GET",
				url:"/api/v1/job/"+job_id,
				success: function(data) {
					if ( (data["status_code"]==1) && (data["results"]) ) {
						M.map.processresults(data.results)
					} else {
						alert("Eh.. job not done?")
					}
				},
				error: function(){
					console.log("Error fetching status!")
				}
			})
		},
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
				M.map.update({
					configkey:results['config_key'],
					mapserver:M.config["mapserver"],
					map:M.config['mapfile'],
					layers:(M.state['layers']==undefined)?defaultLayers:M.state['layers'],
					time:(M.state['time']==undefined)?defaultTime:M.state['time']
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
				M.api.prognosis()
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
			M.api.prognosis()
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
	api: {
		run:function(){
			M.gui.busy('running-model')
			M.gui.notification("0% complete")
			$.ajax({
				type:"POST",
				url:"/api/v1/job",
				data:M.params.serialize(),
				dataType:'json',
				success: function(data) {
					M.state['job_id']=data["job"]
					M.panels.showonly('panel-notifications')
					/*
					jobstatus() starts a loop of requesting job statuses and 
					percent done to see how far along the model run is.
					*/
					M.api.jobstatus()
				},
				error: function(){
					alert("Yikes! An unexpected error occurred!")
				}
			})
		},
		prognosis:function() {
			/*
			Todo: throttle this call somehow, maybe with jquery debounce. When the 
			window is resized by dragging the browser edge it triggers 100s of calls
			to the prognosis because the mapmove event is triggered the whole time.
			Either fix it here, or ensure that the window resize doesnt trigger so
			many mapmove events.
			*/
			M.gui.busy('api-prognosis')
			M.state['prognosis']=false

			/*
			Add a debounce because sometimes one request per map move is too much,
			especially if the user is panning the map and a JSON file with the closest
			chunk needs to be loaded on every move event.
			*/
				$.ajax({
					type:"GET",
					url:"/api/v1/job",
					data:M.params.serialize(),
					dataType:'json',
					success:function(data) {
						console.log("Prognosis for config '"+data["configkey"].substr(0,6)+"': "+data["message"])
						M.map.geojsonlayer.clearLayers()
						M.map.geojsonlayer.addData(data.features)
						M.map.geojsonlayer.bringToFront()
						M.state['prognosis']=true
						M.state['prognosis_message']=data["message"]
						M.gui.done('api-prognosis')
					},
					error:function(xhr){
						M.map.geojsonlayer.clearLayers()
						var data=xhr.responseJSON
						console.log("Prognosis for config '"+data["configkey"].substr(0,6)+"': "+data["message"])
						M.state['prognosis']=false
						M.state['prognosis_message']=data["message"]
						M.gui.done('api-prognosis')
					}
				});
		},
		jobstatus:function() {
			/*
			percent_list is an array which stores the last 5 percentage complete
			that were returned from a status request. As long as these values are
			not all the same, keep requesting a new status <interval> seconds from
			now. When the model has stalled or crashed, the percentage complete 
			will no longer change, then after 5 times we can stop requesting status
			updates and show an error message to the user.

			Todo: check the status_code field. If it's -1 an error has occurred during
			this run.
			*/
			var percent_list = [];
			var identical_timeouts = 25;
			(function updater() {
				$.ajax({
					type:"GET",
					url:"/api/v1/job/"+M.state['job_id'], 
					success: function(data) {
						percent_list.unshift(data["percent_complete"])
						percent_list.splice(identical_timeouts,percent_list.length-identical_timeouts)
						var stopRequestingUpdates=false
						if( (percent_list.length==identical_timeouts) && (M.util.identicalarray(percent_list)) ) {
							stopRequestingUpdates=true
						}

						if( (stopRequestingUpdates==false) && (data["status_code"]==0) ) {
							/* 
							Not complete yet. Schedule another status request. 

							Todo: maybe slowly increase the time of status updates. The longer it 
							takes, the less point there is in updating the status every 2sec.
							*/
							$('div.progress-bar').width(data["percent_complete"]+"%")
							M.gui.notification("Processing: "+data["percent_complete"]+"% complete")
							setTimeout(updater, 2000);
						} 
						else if ( (data["status_code"] == 1) && (data["results"]) ) {
							$('div.progress-bar').width(data["percent_complete"]+"%")
							M.gui.notification("Processing: "+data["percent_complete"]+"% complete")
							M.map.processresults(data.results)
							M.gui.done('running-model')
						}
						else if ( data["status_code"] == -1) {
							M.gui.notification("An error occurred during the model run. <a target='_blank' href='/status/job/"+data["job"]+"'>View the job logfile</a> (new tab) for more information.")
							M.gui.done('running-model')
						}
						else {
							M.gui.notification("Model run reached the timeout at "+data["percent_complete"]+"% complete. <a target='_blank' href='/status/job/"+data["job"]+"'>View the job logfile</a> (new tab) for more information or reload the page at a later time.")
							M.gui.done('running-model')
						}
					},
					error: function(){
						alert("Fetching the job status returned an error. Something went wrong trying to run your model.")
						M.gui.done('running-model')
					}
				})
			})();
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

