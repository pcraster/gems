/*
	Contains utility functions which are used for various purposes
	throughout the app. They can be called as M.util.<function>.
*/
var M=$.extend(M || {},{
	util: {
		linspace:function(d1,d2,n) {
			//linspace.js Generate linearly spaced vectors
			//Helena F. Deus (helenadeus@gmail.com)
			//200809
			//From: http://code.google.com/p/mathbiol/source/browse/linspace.js?repo=compstats
			var j=0;
			var L = new Array();
			while (j<=(n-1)) {
				var tmp1 = j*(d2-d1)/(Math.floor(n)-1);
				var tmp2 = Math.ceil((d1+tmp1)*10000)/10000;
				L.push(tmp2);
				j=j+1;
			}
			return L;
		},
		geohash:function(input) {
			//compute or convert a geohash to or from lat-lng coordinates. Input can 
			//be either a string containing [a-zA-Z0-9] or an array of coordinates.
			//Depending on the type the action should follow.
			//
			console.log("To be implemented...")
		},
		identicalarray:function(array) {
			//checks whether an item in the passed array is not like the others...
		    for(var i=0;i<array.length-1;i++) {
		        if(array[i] != array[i+1]) {
		            return false;
		        }
		    }
		    return true;
		},
		initarray:function(length,value) {
			//creates an array of zeros with the specified length
			var value=(value==undefined)?'':value
			var a=[]
			for(var i=0;i<length;i++) {
				a.push(value)
			}
			return a
		},
		hasownproperties:function(object,properties) {
			var properties = properties.split(" ");
			if (properties.length == 0) {
				return false
			}
			for (var n=0; n<properties.length; n++) {
				if(!object.hasOwnProperty(properties[n])) {
					return false
				}
			}
			return true
		},
		datetotimestamp:function(date) {
			/*
			The javascript Date.toISOString returns a value with milliseconds like
			2014-06-13T22:00:00.000Z, whereas we need one without the last part (e.g. 
			2014-06-13T22:00:00) so that we can pass it in that format to the setTime()
			function.
			*/
			return date.toISOString().substr(0,19)
		},
		timestamptodate:function(timestamp) {
			return new Date(Date.parse(timestamp+"Z"))
		}
	}
})



 