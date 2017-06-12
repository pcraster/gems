var M=$.extend(M || {},{
	'legends':{
		init:function() {
			var Legend = function(el, options) {
				this.el = el
				this.attribute = el.data("legend-for-attribute")
				this.canvas = this.el.find("canvas").first()
				this.elmarker = undefined
				this.options = {
					'min': 		parseFloat(this.canvas.data("min")),
					'max': 		parseFloat(this.canvas.data("max")),
					'ticks': 	this.canvas.data("ticks") ? this.canvas.data("ticks") : 5,
					'marker':   undefined
				}
				$.extend(this.options, options)

				this.init = function() {
					var colorstops = this.canvas.data("color-stops") ? this.canvas.data("color-stops") : "#FFFFFF #000000"
					this.colors = colorstops.split(/[\s]+/).filter(Boolean)
					this.stops = M.util.linspace(0.0,1.0,this.colors.length)
					this.draw()
				}

				this.update = function(options) {
					$.extend(this.options, options)
					this.draw()
				}

				this.marker = function(value) {
					if(this.elmarker == undefined) {
						this.elmarker=this.el.find("li.marker").first()
					}
					if(value == undefined) {
						this.elmarker.hide()
					} else {
						if( (value>this.options.min) && (value<this.options.max) ) {
							this.elmarker.show()
							var left = (value-this.options.min)/(this.options.max-this.options.min)
							this.elmarker.css("left",(100*left)+"%");
							this.elmarker.html("<span>"+this.tickFormatter(value)+"</span>")
						}
					}
				}

				this.tickFormatter = function(value) {
					return parseFloat(value).toFixed(2)
				}

				this.draw = function() {
					if(0 in this.canvas) {
						var ctx = this.canvas[0].getContext("2d")
						var grd = ctx.createLinearGradient(0,0,255,0);
						for(var i=0; i<this.colors.length; i++) {
							grd.addColorStop(this.stops[i],this.colors[i])
						}
						ctx.fillStyle = grd;
						ctx.fillRect(0,0,255,28);
						this.canvas.css("width","100%").css("height", "28px")

						var tick_percentages = M.util.linspace(0,100,this.options.ticks)
						var tick_labels = M.util.linspace(this.options.min, this.options.max, this.options.ticks)
						var ul=$("ul#"+this.canvas.data("ticks-ul")).html("")
						for(var i=0; i<this.options.ticks; i++) {
							var tick_class = ''
							tick_class = (i==0) ? 'first' : tick_class;
							tick_class = (i==(this.options.ticks-1)) ? 'last' : tick_class;
							ul.append("<li style='left:"+tick_percentages[i]+"%' class='"+tick_class+"'>"+this.tickFormatter(tick_labels[i])+"</li>")
						}
						ul.append("<li style='left:20%' class='marker'><span></span></li>")
					}
				}
				this.init()
			}
			$("div.legend-item").each(function(){
				el=$(this)
				if(el.data("legend-for-attribute") != undefined) {
					M.legends.add(new Legend(el))
				}
			});
		},
		get:function(attribute) {
			if ( (attribute == undefined) && (M.legends.active != undefined) ) {
				return M.legends.list[attribute]
			} else {
				return M.legends.list.hasOwnProperty(attribute) ? M.legends.list[attribute] : undefined	
			}
		},
		add:function(legend) {
			M.legends.list=(M.legends.list==undefined)?{}:M.legends.list
			M.legends.list[legend.attribute]=legend
		},
		show:function(attribute) {
			$("div.legend-item").hide()
			M.legends.get(attribute).el.show()
			M.legends.active=attribute
		},
		hide:function(attribute) {
			M.legends.get(attribute).el.hide()
		}
	}
});