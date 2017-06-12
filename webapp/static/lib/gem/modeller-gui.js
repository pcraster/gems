/*
	GEMS Modeller GUI

	This script handles tasks for the graphical user interface, such as enabling
	and disabling buttons, and setting keyboard shortcuts.
*/
var M=$.extend(M || {},{
	'gui': {
		init:function() {
			/*
				Initialize the graphical user interface.
			*/
			M.gui.init_keybindings()
		},
		busy:function(key) {
			/*
				Call M.gui.busy() with the task which is currently happening, for
				example M.gui.busy('running-model') to disble the interface while
				this task is happening. When you're finished with running the model,
				call M.gui.done('running-model'). The list of things we're 'doing' 
				is stored in the M.gui.list variable. When M.gui.done() is called
				and the last item is completed, and we're going no other tasks, 
				the M.gui.enabled() function is called again, enabling the gui again
				for other user input.
			*/
			M.gui.list = 'list' in M.gui ? M.gui.list : []
			if(M.gui.list.indexOf(key) == -1) {
				M.gui.list.push(key)
			}
			M.gui.disable("")
		},
		done:function(key) {
			/*
				Call M.gui.done(<key>) when you're finished (for example in the 
				AJAX success callback of an API request). When there are no more 
				tasks in the list, M.gui.enable() is called.
			*/
			M.gui.list = 'list' in M.gui ? M.gui.list : []
			var index=M.gui.list.indexOf(key)
			if(index != -1) {
				M.gui.list.splice(index, 1)
			}
			if(M.gui.list.length == 0) {
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
			/*
				Disable the run button with <message> in a mouse hover popover.
			*/
			M.menu.run.disable(message)
		},
		notification:function(notification) {
			/*
				Send a notification to the user with a message.
			*/
			$('p#notification-message').html(notification)
		},
		init_keybindings:function() {
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
		}
	}
});