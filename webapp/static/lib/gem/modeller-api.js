/*
	GEMS Modeller API

	This script contains JavaScript functions which communicate with the
	GEMS API. Each API call has its own function in M.api.<name>. When some
	sort of critical error occurs (i.e. one that will prevent the application
	from working as intended) a call is made to M.criticalerror() with some
	information as to what happened. The M.criticalerror will show some sort
	of alert notifying the user that an error occurred.
*/
var M=$.extend(M || {},{
	'api': {
		status:function() {
			/*
				M.api.status()

				Status call checks whether the GEMS API can be reached, and 
				whether the token we're providing is valid.
			*/
			$.ajax({
				type:"GET",
				url:M.config["api"],
				dataType:'json',
				headers: {
					"Authorization": M.config["api_auth"]
				},
				success: function(data) {
					if(data['authenticated'] == true) {
						console.log("Successfully authenticated to GEMS API.")
					} else {
						M.api.error(undefined, "Failed to connect/authenticate to GEMS API.")
					}
				},
				error: function() {
					M.api.error(undefined, "Failed to connect/authenticate to GEMS API.")
				}
			});
		},
		config_status:function(config_key){
			/*
				M.api.config(config_key)

				Requests a configuration from the API with the given config key.
				If no config key or an invalid config key is supplied a 404 not found
				will be returned. 
			*/
			$.ajax({
				type:"GET",
				url:M.config["api"]+"config/"+config_key,
				dataType:'json',
				headers: {
					"Authorization": M.config["api_auth"]
				},
				success: function(data) {
					console.log("Retrieved configuration data for config '"+config_key.substr(0,6)+"':")
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
				error: function(xhr) {
					M.api.error(xhr)
				}
			});
		},
		/*
			M.api.job_create()

			Executes a POST request to the /job/ endpoint in order to schedule
			a modellingg job.
		*/
		job_create:function(){
			M.gui.busy('running-model')
			M.gui.notification("0% complete")
			$.ajax({
				type:"POST",
				url:M.config["api"]+"job",
				data:M.params.serialize(),
				dataType:'json',
				headers: {
					"Authorization": M.config["api_auth"]
				},
				success: function(data) {
					M.state['job_id']=data["job"]
					M.panels.showonly('panel-notifications')
					/*
					M.api.job_status() starts a loop of requesting job statuses and 
					percent done to see how far along the model run is.
					*/
					M.api.job_status()
				},
				error: function(xhr){
					M.gui.done('running-model')
					M.api.error(xhr)
				}
			})
		},
		job_prognosis:function() {
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
				type: "GET",
				url: M.config["api"]+"job",
				data: M.params.serialize(),
				dataType: 'json',
				headers: {
					"Authorization": M.config["api_auth"]
				},
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
					M.gui.done('api-prognosis')
					if('responseJSON' in xhr) {
						/*
						An error on a prognosis API call is not critical, but more representative
						of a situation where the model simply can't be run at that location, or
						that it has been run here before with the same config, so there is no point
						in doing it again.
						*/
						var data=xhr.responseJSON
						console.log("Prognosis for config '"+data["configkey"].substr(0,6)+"': "+data["message"])
						M.state['prognosis']=false
						M.state['prognosis_message']=data["message"]
					} else {
						/*
						However, if there is no JSON content then something did go wrong!
						*/
						M.api.error(xhr)
					}
					
				}
			});
		},
		job_log:function(job_uuid) {
			/*
			Show a modal dialog with a logfile of the job in it. This is for debugging
			purposes or to check why a model run failed.
			*/
				$.ajax({
					type:"GET",
					url:M.config["api"]+"job/"+job_uuid+"/log", 
					headers: {
						"Authorization": M.config["api_auth"]
					},
					success: function(data) {
						$('#log-modal-content').html(data)
						$('#log-modal').modal()
					},
					error: function(xhr){

					}
				})



		},
		job_status:function() {
			/*
			percent_list is an array which stores the last 5 percentage complete
			that were returned from a status request. As long as these values are
			not all the same, keep requesting a new status <interval> seconds from
			now. When the model has stalled or crashed, the percentage complete 
			will no longer change, then after 5 times we can stop requesting status
			updates and show an error message to the user.

			Todo: check the status_code field. If it's -1 an error has occurred during
			this run.

			Todo: Rather than use this polling method, implement a solution using
			EventStream, that's much more efficient. The API should eventstream from
			some job status endpoint like /job/<jobid>/eventstream. When the run is
			complete or an error occurs, cancel the eventstream and reset the gui
			as usual.
			*/
			var percent_list = [];
			var identical_timeouts = 25;
			(function updater() {
				$.ajax({
					type:"GET",
					url:M.config["api"]+"job/"+M.state['job_id'], 
					headers: {
						"Authorization": M.config["api_auth"]
					},
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
							M.gui.notification("Processing: "+data["percent_complete"]+"% complete. <a href='javascript:M.api.job_log(\""+data["job"]+"\");'>View log</a>.")
							M.map.processresults(data.results)
							M.api.job_prognosis()
							M.gui.done('running-model')
						}
						else if ( data["status_code"] == -1) {
							M.gui.notification("An error occurred during the model run. <a href='javascript:M.api.job_log(\""+data["job"]+"\");'>View the job logfile</a> for more information.")
							M.gui.done('running-model')
						}
						else {
							M.gui.notification("Model run reached the timeout at "+data["percent_complete"]+"% complete. <a href='javascript:M.api.job_log(\""+data["job"]+"\");'>View the job logfile</a> for more information or reload the page at a later time.")
							M.gui.done('running-model')
						}
					},
					error: function(xhr){
						M.gui.done('running-model')
						M.gui.error(xhr)
					}
				})
			})();
		},
		error: function(xhr, message) {
			/*
				This error function is called when an API triggers an error response. We check
				the response for a responseJSON attribute, signifying that at least we got some
				sort of json response, usually with a 'message' attribute. 
			*/
			if(message) {
				alert("An API error occurred!\n\n"+message)
			} else {
				if("responseJSON" in xhr) {
					alert("An API error occurred!\n\nStatus: "+xhr.status+"\n"+xhr.responseJSON['message'])
				} else {
					alert("An API error occurred!\n\nStatus: "+xhr.status+"\nNo JSON content could be decoded.")
				}
			}
		}
	}
});