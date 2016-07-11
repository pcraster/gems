var M=$.extend(M || {},{
	'charts':{
		init:function() {
			console.log("Looking for chart placeholders")
			var Timeseries = function(el, options) {
				this.el = el
				this.id = el.data("chart-id")
				this.placeholder = $("#legend-chart-timeseries-placeholder")
				this.gridMarkings = []
				this.options = {
					'time':''
				}
				$.extend(this.options, options)

				/*
				Bind some events to the placeholder for clicking and hovering on
				data points in the plot. These need to be bound only once, and they'll
				stick to the placeholder even if the chart gets redrawn in the meantime.
				*/
				this.placeholder.bind("plotclick", $.proxy(function (event, pos, item) {
					if (item) {
						var timestamp = new Date(item.datapoint[0])
						var value = item.datapoint[1]
						M.map.setTime(M.util.datetotimestamp(timestamp))
						var legend = M.legends.get(M.state['layers'])
						this.defaultvalue=item.datapoint[1]
						legend.marker(this.defaultvalue)
					}
				},this));
				
				this.placeholder.bind("plothover", $.proxy(function (event, pos, item) {
					var legend = M.legends.get(M.state['layers'])
					if(item) {
						legend.marker(item.datapoint[1])
						this.placeholder.addClass("clickable");
					} else {
						legend.marker(this.defaultvalue)
						this.placeholder.removeClass("clickable");
					}
				},this));

				this.update = function(options) {
					$.extend(this.options, options)
					this.load()
				}

				this.load = function() {
					if(M.util.hasownproperties(this.options,"lat lng layers time configkey")) {
						this.placeholder.addClass('loading')
						$.ajax({
							type: "GET",
							url: "/data/point",
							data: this.options,
							dataType: 'json',
							success: this.setData,
							context: this,
							error:function(xhr){
								console.log("error fetching chart.")
							}
						})
					} else {
						this.el.hide()
					}
				}

				this.setTime = function(timestamp) {
					if (this.data != undefined) {
						this.options['time'] = timestamp;
						this.draw()
					}
				}

				this.setData = function(data) {
					this.data = data
					this.draw()
				}

				this.draw = function() {
					console.log("drawing chart! time="+this.options['time'])

					var data = this.data;

					this.gridMarkings=[]
					if (data != undefined) {
						this.gridMarkings=[]
						var legend = M.legends.get(M.state['layers'])
						this.defaultvalue=data.currentvalue
						legend.marker(this.defaultvalue)
						for (var n = 0; n < data["value"].length; n+=1) {
							if (data["timestamp"][n]==this.options['time']) {
								this.gridMarkings = [{ xaxis: { from: n-0.5, to: n+0.5}, color: "yellow" }]
							}
						}
					}
					/*
					Update the timeseries chart with new data.
					*/
					var chartOptions = data.hasOwnProperty("yaxis") ? $.extend({}, M.charts.defaultOptions, {'yaxes':[data['yaxis']]}):M.chart.defaultOptions;

					var numValues = data.hasOwnProperty("value") ? data["value"].length : 0
					var numTimestamps = data.hasOwnProperty("timestamp") ? data["timestamp"].length : 0

					if( (numValues == numTimestamps) && (numValues > 1) && (numTimestamps > 1) ) {
						console.log("Looks like we have some plottable data, show timeseries chart and update it.")
						var series = []
						var series2 = []
						for (var n = 0; n < data["value"].length; n+=1) {
							var timestamp = M.util.timestamptodate(data["timestamp"][n])
							series.push([timestamp.getTime(), data["value"][n]])
							series2.push([n,-9999])
						}
						var chartData = [
							{ data: series2, color: '#15b01a',  xaxis: 1 },
							{ data: series, color: '#e50000', xaxis: 2 }
						]
						this.el.show()
						this.placeholder.removeClass('loading')

						chartOptions['grid']['markings'] = this.gridMarkings;

						$.plot(this.placeholder, chartData, chartOptions);

					} else {
						this.el.hide()
						console.log("Hmm no point in plotting this really...")
					}

				}
			}

			$("div.legend-chart").each(function(){
				el=$(this)
				if(el.data("chart-id") != undefined) {
					M.charts.add(new Timeseries(el))
				}
			});
		},
		get:function(id) {
			if ( (id == undefined) && (M.charts.active != undefined) ) {
				return M.charts.list[id]
			} else {
				return M.charts.list.hasOwnProperty(id) ? M.charts.list[id] : undefined	
			}
		},
		add:function(chart) {
			M.charts.list=(M.charts.list==undefined)?{}:M.charts.list
			M.charts.list[chart.id]=chart
		},
		show:function(id) {
			M.charts.get(id).el.show()
			M.charts.active=id
		},
		hide:function(id) {
			M.legends.get(id).el.hide()
		},
		defaultOptions:{
			color: "rgb(255,50,50)",
			series: {
				lines: { 
					show: true,
					color: "rgb(255,50,50)", 
					fill: false,
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
				markings: [/*
					{ xaxis: { from: 7.5, to: 8.5 }, color: "yellow" } ,
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
	                	//ticks:12,
	                	//min:-0.5,
	                	//max:12,
	                	tickDecimals:0,
	                	alignTicksWithAxis:1
	                },
					{
						mode: "time"
						//alignTicksWithAxis:1
					} 
            ]
		}
	}
});