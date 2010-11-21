/* 
  Dracones Web-Mapping Framework
  ==============================

  http://surveillance.mcgill.ca/dracones
  Copyright (c) 2009, Christian Jauvin
  All rights reserved. See LICENSE.txt for BSD license notice
*/ 


/** 
    Dracones module (provides only one instantiable class).
    @namespace 
    @author Christian Jauvin cjauvin[at]gmail[dot]com
    @version 1.1.2
*/
var dracones = dracones || (function() {

    // Firebug detection
    if (typeof console === 'undefined') {
        console = {
            log: function() { return false; },
            error: function() { return false; }
        };
    }

    // jQuery is mandatory from this point
    if (typeof jQuery === 'undefined') {
        console.error("Dracones Client Error: could not load jQuery library.. cannot go further..");
        alert("Dracones Client Error: could not load jQuery library.. cannot go further..");
        return false;
    }

    // make sure that all Dracones ajax queries are not cached
    jQuery.ajaxSetup({cache:false})
    var ajaxq_name = "dracones";

    // Find base URL where dracones.js is being executed, to build the Python ajax command URLS 
    var dracones_url = null;
    var scripts = document.getElementsByTagName('script');
    for (var i = 0; i < scripts.length; i++) {
        var m = scripts[i].src.match(/(.*)\/javascript\/dracones.js$/);
        if (m) {
            dracones_url = m[1];
        }        
    }
    if (!dracones_url) {
        console.error("Dracones Client Error: could not derive 'dracones_url' JavaScript variable (hint: try to set it yourself in dracones.js)");
        alert("Dracones Client Error: could not derive 'dracones_url' JavaScript variable (hint: try to set it yourself in dracones.js)");
        return false;
    }

    // private dracones module level functions
    // ---------------------------------------

    var getAbsolutePosition = function(element) {
        var r = { x: element.offsetLeft, y: element.offsetTop };
        if (element.offsetParent) {
            var tmp = getAbsolutePosition(element.offsetParent);
            r.x += tmp.x;
            r.y += tmp.y;
        }
        return r;
    };

    // geographical to pixel coords
    var geo2pix = function(xt, gx, gy, w, h) {
        var _geo2pix = function(geo_pos, pix_min, pix_max, geo_min, geo_max, inv) {
            w_geo = Math.abs(geo_max - geo_min);
            w_pix = Math.abs(pix_max - pix_min);
            if (w_geo <= 0) return 0
            g2p = w_pix / w_geo
            if (inv) del_geo = geo_max - geo_pos
            else del_geo = geo_pos - geo_min
            del_pix = del_geo * g2p
            pos_pix = pix_min + del_pix
            return parseInt(pos_pix)
        };
        var px = _geo2pix(gx, 0, w, xt.minx, xt.maxx, false);
        var py = _geo2pix(gy, 0, h, xt.miny, xt.maxy, true);
        return { x : px, y : py };
    };

    // returns: { 'btn' : [left|right|none] 'mod' : [shift|ctrl|alt|none]}
    // !!! alt is not working in IE
    var getMouseEventValues = function(event) {
        var val = { 'btn' : 'none', 'mod' : 'none' };
        if (event.button == 0 || event.button == 1) {
            val.btn = 'left';
        } else if (event.button == 2) {
            val.btn = 'right';
        }
        if (event.shiftKey) {
            val.mod = 'shift';
        } else if (event.altKey) {
            val.mod = 'alt';
        } else if (event.ctrlKey || event.metaKey) { // metaKey detects the Apple/command key on FF for OSX
            val.mod = 'ctrl';
            // Correct a FF/OSX strange behavior with CTRL + left button: event.button=2 when it should be 0
            if (navigator.appCodeName == 'Mozilla' && navigator.userAgent.indexOf('OS X') != -1 && val.btn == 'right') {
                val.btn = 'left';
            }
        }
        return val;
    };

    var areExtentsEqual = function(xt1, xt2) {
        return (xt1.minx == xt2.minx && 
                xt1.maxx == xt2.maxx && 
                xt1.miny == xt2.miny && 
                xt1.maxy == xt2.maxy);
    };

    /////////////////////////////////
    // dracones module public part //
    /////////////////////////////////

    /** @scope dracones */
    return {

        /**  
           dracones module script url export
           @public
         */
        url: dracones_url,

        /** 
           Dracones map widget, anchored in an existing div element.

           @constructor
           @param {obj} config An object containing the parameters.
           @param {str} config.anchor_elem The id of the supplied anchor div (must exist).
           @param {str} config.app_name Name of the application.
           @param {str} config.mid Widget/map instance ID, to distinguish among multiple map widgets on the same page.
           @param {str[]} config.init_dlayers List of DLayers to initialize at startup. (A single string instead of a list is allowed).
           @param {str} [config.point_action] The action to trigger when CTRL + single clicking. For the moment, only "select" and "draw" are defined and meaningful.
           @param {str[]} [config.point_action_dlayers] List of DLayers on which the point action must be performed. (A single string instead of a list is allowed).
           @param {str} [config.box_action] The action to trigger when CTRL + left dragging the mouse (box select). For the moment, only "select" is defined.
           @param {str[]} [config.box_action_dlayers] List of DLayers on which the box action must be performed. (A single string instead of a list is allowed).
           @param {int} [config.history_size=1] Number of steps kept in history memory.
           @param {str} [config.undo_control_id] The DOM ID of a control (presumbaly a button) to which will be attached the "Undo" function, as well as "bound" detection
                                                 mechanism that will disable it when undo is no longuer possible.
           @param {str} [config.redo_control_id] The DOM ID of a control (presumbaly a button) to which will be attached the "Redo" function, as well as "bound" detection
                                                 mechanism that will disable it when redo is no longuer possible.
           @param {bool} [config.prevent_click_binding] Set to true if for some reason you want to bind the history to something 
                                                        other than the click handler of the controls.
           @param {bool} [config.delayed_init=false] If set to true, the init function must be called manually (useful in case a login screen is used, for instance).
           @param {int} [config.map_size_rel_to_vp=3] Number of times that the underlying MS map is greater than the viewport. <b>This value must be odd and >= 3</b>.
           @param {str} [config.select_mode] How selection is to be performed on a DLayer: "reset" (default) will unselect all features before selecting new ones, 
                                             "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
                                             Note that this mode affects all the selection mechanisms: mouse (point/box selection) as well as calls to the selectFeatures method.

           @example
           var mw = new dracones.MapWidget({
               anchor_elem: 'map_widget_anchor_div', 
               app_name: 'my_app', 
               mid: 'my_app_map_widget_1', 
               map: 'some_map', 
               init_dlayers: ['circle', 'region'], 
               point_action: 'draw',
               point_action_dlayers: ['circle', 'region'],
               box_action: 'select',
               box_action_dlayers: 'region',
               map_size_rel_to_vp: 5
           });
          */
        MapWidget: function(config) {
                            
            var that = this;

            var DEFAULT_MAP_SIZE_REL_TO_VP = 3;
            var DEBUG_MAP_PANNING = false;

            if (!config.hasOwnProperty('map_size_rel_to_vp')) {
                config.map_size_rel_to_vp = DEFAULT_MAP_SIZE_REL_TO_VP;
            } else if (config.map_size_rel_to_vp % 2 != 1 || config.map_size_rel_to_vp < 3) {
                console.error('Warning: map_size_rel_to_vp must be odd and greater than 3 (it has been set to 3)');
                config.map_size_rel_to_vp = DEFAULT_MAP_SIZE_REL_TO_VP;
            }

            // map viewport dimension, extracted from the anchor div
            // this should be: map width / 3, map height / 3
            var map_vp_width = parseInt(jQuery('#' + config.anchor_elem).css('width'));
            var map_vp_height = parseInt(jQuery('#' + config.anchor_elem).css('height'));
            // This corresponds to the number of viewports in the unseen, overflow left or upper part at 
            // the left of the widget.. eg. if config.map_size_rel_to_vp==3, it is 1, and if config.map_size_rel_to_vp==5, it is 2
            var hnvp = (config.map_size_rel_to_vp - 1) / 2; // half n viewports
            var moving_anchor_base_pos = {x: (hnvp * -map_vp_width),
                                          y: (hnvp * -map_vp_height) };

            // zoom size
            var zsize = 2;

            // Action bookkeeping
            var action_register = {
                select: {
                    url: dracones_url + '/dracones_do/action',
                    callback: function(resp) {}
                },
                draw: {
                    url: dracones_url + '/dracones_do/action',
                    callback: function(resp) { }
                }
            };

            // if set, called by handleSuccess when it's done
            var success_callback = null;

            // click/dblclick distinction mechanism
            var click_timeout = null;
            var click_timeout_delay = 300;
            
            // current map extent (coming from server)
            var curr_extent = {
                minx: -1.0,
                miny: -1.0,
                maxx: -1.0,
                maxy: -1.0
            };

            // viewport
            var vp = jQuery('<div />').appendTo(jQuery('#' + config.anchor_elem));
            vp.css({
                position: 'absolute',
                overflow: DEBUG_MAP_PANNING ? 'visible' : 'hidden',
                border: '0px solid black',
                width: map_vp_width,
                height: map_vp_height
            });

            var vp_pos = getAbsolutePosition(vp[0]);

            // Loading label (public for allowing external access through MapWidget instance)
            this.loading = jQuery('<div>Loading...</div>').appendTo(vp);
            this.loading.css({
                position: 'absolute',
                background: 'yellow',
                border: '1px solid black',
                left: 0,
                top: 0,
                'z-index': 1000
            });
            this.loading.hide();

            // Marker that appears on point location whenever point zoom is triggered (public for allowing external access through MapWidget instance)
            this.point_zoom_marker = jQuery('<div />').appendTo(vp);
            this.point_zoom_marker.css({
                position: 'absolute',
                width: 32,
                height: 32,
                left: 0,
                top: 0,
                'z-index': 1001
            });
            this.point_zoom_marker.hide();

            // This function is called whenever a map image is returned by Dracones.
            // It performs the positioning computations first on an alternate, hidden moving_anchor/image, and when done,
            // switches the current and alternate moving_anchor/image, to prevent flickering.
            var mapImageLoadCallback = function() {

                var vpt = that.getViewportTranslation();

                // center vp: after requests that should "reset" the map position to its initial value (zoom, full extent, etc.)
                if (center_viewport) {
                    var adjust = {x: 0, y: 0 };
                // if not: put back the modified map at exactly the same place it was before the request (selection, query, etc.)
                } else {
                    var adjust = {x: vpt.x, y: vpt.y };
                }

                // after pan: put pack the map to where it was, but by taking into account the extent 
                // that was updated in one of four directions
                if (pan_dir == 'right') {
                    adjust.x = vpt.x - ((hnvp - 0.5) * map_vp_width);
                } else if (pan_dir == 'left') {
                    adjust.x = vpt.x + ((hnvp - 0.5) * map_vp_width);
                } else if (pan_dir == 'up') {
                    adjust.y = vpt.y  + ((hnvp - 0.5) * map_vp_height);
                } else if (pan_dir == 'down') {
                    adjust.y = vpt.y  - ((hnvp - 0.5) * map_vp_height);
                }

                getAlternateMovingAnchor().css({'left': moving_anchor_base_pos.x - adjust.x,
                                                'top': moving_anchor_base_pos.y - adjust.y});

                getCurrentMovingAnchor().css('visibility', 'hidden');
                getAlternateMovingAnchor().css('visibility', 'visible');
                curr_moving_anchor = (curr_moving_anchor + 1) % 2;

                center_viewport = false;
                pan_locked = false;

                that.loading.hide();

                checkForPanOverflow();

                init_completion_check_passed = true;

            };

            // First moving anchor div, on which the first map img is attached
            var moving_anchor = jQuery('<div />').appendTo(vp);
            moving_anchor.css({
                position: 'absolute',
                visibility: 'visible',
                left: moving_anchor_base_pos.x,
                top: moving_anchor_base_pos.y
            });

            // First map image, attached to moving_anchor
            var map_img = jQuery('<input type="image" />').appendTo(moving_anchor);
            map_img.css({
                cursor: 'default',
                border: '1px dashed gray',
                outline: 'none'
            });            
            if (DEBUG_MAP_PANNING) {
                map_img.css({
                    opacity: 0.5, 
                    filter: 'alpha(opacity=50)'
                });
            }
            moving_anchor.map_img = map_img;
            map_img.attr('oncontextmenu', 'return false'); // this seems to be working only in Firefox
            map_img.mousedown(clickDownHandler);
            map_img.dblclick(doubleClickHandler);
            map_img.mousewheel(pointZoom);
            map_img.bind('mousemove', testHover);          
            map_img.bind('dragstart', function() { return false; }); // prevents img selection in Chrome

            // This function is called whenever the map img has finished loading
            map_img.bind('load', mapImageLoadCallback);

            // Second moving anchor div, on which the second map img is attached; used to prevent flickering while performing positioning computations.
            var moving_anchor2 = jQuery('<div />').appendTo(vp);
            moving_anchor2.css({
                position: 'absolute',
                visibility: 'hidden',
                left: moving_anchor_base_pos.x,
                top: moving_anchor_base_pos.y
            });

            // Second map image
            var map_img2 = jQuery('<input type="image" />').appendTo(moving_anchor2);
            map_img2.css({
                cursor: 'default',
                border: '1px dashed gray', 
                outline: 'none'
            });            
            if (DEBUG_MAP_PANNING) {
                map_img2.css({
                    opacity: 0.5, 
                    filter: 'alpha(opacity=50)'
                });
            }
            moving_anchor2.map_img = map_img2;
            map_img2.attr('oncontextmenu', 'return false'); // this seems to be working only in Firefox
            map_img2.mousedown(clickDownHandler);
            map_img2.dblclick(doubleClickHandler);
            map_img2.mousewheel(pointZoom);
            map_img2.bind('mousemove', testHover);          
            map_img2.bind('dragstart', function() { return false; }); // prevents img selection in Chrome

            // This function is called whenever the map img has finished loading
            map_img2.bind('load', mapImageLoadCallback);

            // Both moving_anchors
            var moving_anchors = [moving_anchor, moving_anchor2];
            var curr_moving_anchor = 0; // can only be 0 or 1 (index into moving_anchors array, which has 2 elems)

            /** @private */
            function getCurrentMovingAnchor() {
                return moving_anchors[curr_moving_anchor];
            };

            /** @private */
            function getAlternateMovingAnchor() {
                return moving_anchors[(curr_moving_anchor + 1) % 2];
            };

            /** @private */
            function getCurrentMovingAnchorPos() {
                return {x: parseInt(getCurrentMovingAnchor().css('left')),
                        y: parseInt(getCurrentMovingAnchor().css('top')) };
            };

            // selection box
            var select_box = jQuery('<div />').appendTo(vp);
            select_box.css({
                'background-color': 'blue',
                position: 'absolute',
                'z-index': 1000,
                opacity: 0.3,
                filter: 'alpha(opacity=30)'
            });
            select_box.hide();
            var select_box_init_pos = { x:0, y:0 };

            if (!config.hasOwnProperty('select_mode')) {
                config.select_mode = 'reset';
            }

            /* mouse hover (mouseover/tooltip)
               -------------------------------
               Contains objects of type: { gx, gy, px, py, html } 
               gx,gy: geo coords
               px,py: pixel (map) coords
               A couple gx,gy is returned once by a server query; it stays in the structure until further notice
               Every time the map extent changes (zoom, pan..) the (px,py) couples  are recomputed, client-side
               via a call to updateHoverMapWithNewExtent()
            */
            var hover = jQuery('<div />').appendTo(vp);
            hover.css({
                'font-size': '0.8em',
                border: '1px solid black', 
                background: '#ffffe0', 
                position: 'absolute',
                'z-index': 1000,
                padding: '0 0 0 0'
            });
            hover.hide();

            if (!config.hasOwnProperty('history_size') || config.history_size < 1) {
                config.history_size = 1;
            }

            var hover_maps = []; // list of: { dlayer -> [{gx,gy,px,py,html}] }
            var resetHoverMaps = function() {
                for (var i = 0; i < config.history_size; i++) {
                    hover_maps[i] = {};
                }
            };
            resetHoverMaps();
            var history_idx = config.history_size - 1;
                
            // map positioning global state variables
            var prev_pan_pos = {x:0, y:0};
            var pan_locked = false;
            var pan_dir = null;
            var center_viewport = false;

            // transform some list params that can be allowed as strings
            if (typeof config.init_dlayers === 'string') {
                config.init_dlayers = [config.init_dlayers];
            }
            if (typeof config.point_action_dlayers === 'string') {
                config.point_action_dlayers = [config.point_action_dlayers];
            }
            if (typeof config.box_action_dlayers === 'string') {
                config.box_action_dlayers = [config.box_action_dlayers];
            }

            // undo/redo automatic control click bindings
            if ((config.hasOwnProperty('prevent_click_binding') && !config.prevent_click_binding) || !config.hasOwnProperty('prevent_click_binding')) {
                if (config.hasOwnProperty('undo_control_id')) {
                    jQuery('#' + config.undo_control_id).click(function() {
                        that.history({direction: 'undo'});
                    });
                }
                if (config.hasOwnProperty('redo_control_id')) {
                    jQuery('#' + config.redo_control_id).click(function() {
                        that.history({direction: 'redo'});
                    });
                }
            }

            // A completion test is triggered at the end of init, that verifies that 
            // a first map image has been correctly loaded. If it passes, it won't be called
            // until next init, and if it does not, it shows a diagnostic error message that 
            // will likely help to debug.
            var init_completion_check_required = true;
            var init_completion_check_passed = false;

            /** @private */
            function clickDownHandler(event) {
                
                var mev = getMouseEventValues(event);
                if (mev.btn != 'left') return; // only act on left click

                // set double-click listener
                if (!click_timeout) {
                    click_timeout = setTimeout(function() {
                        click_timeout = null;
                        singleClickHandler(event);
                    }, click_timeout_delay);
                }

                hover.hide();

                // map nav

                if (mev.mod == 'none') {

                    prev_pan_pos = {x:event.pageX, y:event.pageY };

                    for (var i = 0; i < 2; i++) {
                        moving_anchors[i].map_img.unbind('mousemove', testHover);
                        moving_anchors[i].map_img.bind('mousemove', panMove);
                        moving_anchors[i].map_img.bind('mouseup', panUp);
                        moving_anchors[i].map_img.css('cursor', 'move');
                    }

                // select or zoom box

                } else if (mev.mod == 'shift' || mev.mod == 'ctrl') {

                    select_box_init_pos = {x: event.pageX, y: event.pageY };

                    select_box.bind('mousemove', selectBoxMove);
                    select_box.bind('mouseup', selectBoxUp);

                    for (var i = 0; i < 2; i++) {
                        moving_anchors[i].map_img.unbind('mousemove', testHover);
                        moving_anchors[i].map_img.bind('mousemove', selectBoxMove);
                        moving_anchors[i].map_img.bind('mouseup', selectBoxUp);
                    }

                    if (mev.mod == 'ctrl') {

                        select_box.css({
                            border: '',
                            'background-color': 'blue'
                        });
                        select_box.context = 'select';

                    } else if (mev.mod == 'shift') {

                        select_box.css({
                            border: '2px dashed black',
                            'background-color': ''
                        });
                        select_box.context = 'zoom';
                    }

                } 
            };

            /** @private */
            function panMove(event) {

                clearClickTimeout();
                var diff = {x: event.pageX - prev_pan_pos.x, y:event.pageY - prev_pan_pos.y};
                prev_pan_pos = {x: event.pageX, y:event.pageY};
                var ma_pos = getCurrentMovingAnchorPos();
                getCurrentMovingAnchor().css({'left': ma_pos.x + diff.x, 
                                              'top': ma_pos.y + diff.y});                    
                checkForPanOverflow();
                
            };
                
            /**
               check for pan overflow (if not already treating a request) 
               @private */
            function checkForPanOverflow() {

                if (!pan_locked) {

                    var ma_pos = getCurrentMovingAnchorPos();
                    var dir = null;
                    // these could be replaced probably by easier to read VP translation computations
                    var right_limit = ((config.map_size_rel_to_vp - 1) * -map_vp_width) + (map_vp_width / 2);
                    var left_limit = -(map_vp_width / 2);
                    var down_limit = ((config.map_size_rel_to_vp - 1) * -map_vp_height) + (map_vp_height / 2);
                    var up_limit = -(map_vp_height / 2);

                    if (ma_pos.x <= right_limit) {
                        dir = 'right';
                    } else if (ma_pos.x >= left_limit) {
                        dir = 'left';
                    } else if (ma_pos.y <= down_limit) {
                        dir = 'down';
                    } else if (ma_pos.y >= up_limit) {
                        dir = 'up';
                    }

                    if (dir) { // pan overflow triggered
                        
                        pan_locked = true;                        
                        that.loading.show();
                        jQuery.ajaxq(ajaxq_name, {
                            type: 'GET',
                            url: dracones_url + '/dracones_do/pan',
                            dataType: 'json',
                            data: {
                                mid: config.mid,
                                dir: dir
                            },
                            success: that.handleSuccess,
                            error: that.handleError
                        });
                    }
                }
            };

            /** @private */
            function panUp(event) {
                for (var i = 0; i < 2; i++) {
                    moving_anchors[i].map_img.unbind('mousemove', panMove);
                    moving_anchors[i].map_img.unbind('mouseup', panUp);
                    moving_anchors[i].map_img.css('cursor', 'default');
                    moving_anchors[i].map_img.bind('mousemove', testHover);
                }
            };

            /** @private */
            function clearClickTimeout() {
                if (click_timeout) {
                    clearTimeout(click_timeout);
                    click_timeout = null;
                }
            };

            // 
            /** this is called directly by clbclick handler 
               @private 
              */
            function doubleClickHandler(event) {                
                clearClickTimeout();
                // this could be something else of course
                pointZoom(event);
            };
            
            /** @private */
            function pointZoom(event, delta) {
                // convert click coords to map coords
                var ma_pos = getCurrentMovingAnchorPos();
                var mev = getMouseEventValues(event);
                // if mousewheel delta is found, override modifier
                if (typeof delta !== 'undefined') {
                    mev.mod = delta<0 ? 'shift' : '';
                }
                that.point_zoom_marker.css({
                    left: event.pageX - vp_pos.x - 16,
                    top: event.pageY - vp_pos.y - 16,
                    'background-image': 'url(' + dracones_url + '/img/Arrow_' + (mev.mod=='shift'?'out':'in') + '.png)'
                }); 
                that.point_zoom_marker.show();
                that.loading.show();                    
                jQuery.ajaxq(ajaxq_name, {
                    type: 'GET',
                    url: dracones_url + '/dracones_do/zoom',
                    dataType: 'json',
                    data: {
                        mid: config.mid,
                        mode: mev.mod == 'shift' ? 'out' : 'in',
                        zsize: zsize,
                        x: event.pageX - vp_pos.x + map_vp_width + (-map_vp_width - ma_pos.x),
                        y: event.pageY - vp_pos.y + map_vp_height + (-map_vp_height - ma_pos.y)
                    },
                    success: that.handleSuccess,
                    error: that.handleError
                });
                return false;
            };

            /** @private */
            function singleClickHandler(event) {
                pointAction(event);
            }

            /** @private */
            function pointAction(event) {
                if (!config.hasOwnProperty('point_action') || !config.hasOwnProperty('point_action_dlayers')) { return; }
                var ma_pos = getCurrentMovingAnchorPos();
                var mev = getMouseEventValues(event);
                if (mev.mod != 'ctrl') { return; }
                that.loading.show();
                jQuery.ajaxq(ajaxq_name, {
                    type: 'GET',
                    url: action_register[config.point_action].url,
                    dataType: 'json',
                    data: {
                        mid: config.mid,
                        action: config.point_action,
                        select_mode: config.select_mode,
                        x: event.pageX - vp_pos.x - ma_pos.x,
                        y: event.pageY - vp_pos.y - ma_pos.y,
                        dlayers: config.point_action_dlayers.join(',')
                    },
                    success: function(resp) {
                        action_register[config.point_action].callback(resp);
                        that.handleSuccess(resp);
                    },
                    error: that.handleError
                });               
            };

            /** boundaries in viewport coord: {x:left, y:top, w:widgh, h:height}
                @private */
            function getSelectBoxBoundaries(event) {
                var w = event.pageX - select_box_init_pos.x;
                var h = event.pageY - select_box_init_pos.y;
                if (w < 0) {
                    var x = (select_box_init_pos.x + w);
                } else {
                    if (select_box_init_pos.x + w > map_vp_width + vp_pos.x) { // detection limite droite
                        w = map_vp_width - select_box_init_pos.x;
                    }
                    var x = select_box_init_pos.x;
                }
                if (h < 0) {
                    var y = (select_box_init_pos.y + h);
                } else {
                    var y = select_box_init_pos.y;
                }
                //return [x, y, Math.abs(w), Math.abs(h)];
                return { x: x, y: y, w: Math.abs(w), h: Math.abs(h) };
            };

            /** @private */
            function selectBoxMove(event) {
                clearClickTimeout();
                var box = getSelectBoxBoundaries(event);
                select_box.css({
                    left: box.x - vp_pos.x,
                    top: box.y - vp_pos.y,
                    width: box.w,
                    height: box.h
                });
                select_box.show();
            };

            /** @private */
            function selectBoxUp(event) {

                for (var i = 0; i < 2; i++) {
                    moving_anchors[i].map_img.unbind('mousemove', selectBoxMove);
                    moving_anchors[i].map_img.unbind('mouseup', selectBoxUp);
                    moving_anchors[i].map_img.bind('mousemove', testHover);
                }

                select_box.unbind('mousemove');
                select_box.unbind('mouseup');

                select_box.css({
                    width: 0,
                    height: 0
                });

                select_box.hide();

                // false box, considered a click
                if (Math.abs(select_box_init_pos.x - event.pageX) <= 5 ||
                    Math.abs(select_box_init_pos.y - event.pageY) <= 5) {
                    
                } else {
                    
                    var boundaries = getSelectBoxBoundaries(event);
                    var ma_pos = getCurrentMovingAnchorPos();
                    boundaries.x -= vp_pos.x;
                    boundaries.y -= vp_pos.y;
                    boundaries.x += -ma_pos.x;
                    boundaries.y += -ma_pos.y;

                    // box zoom
                    if (select_box.context == 'zoom') {

                        that.loading.show();
                        jQuery.ajaxq(ajaxq_name, {
                            type: 'GET',
                            url: dracones_url + '/dracones_do/zoom',
                            dataType: 'json',
                            data: {
                                mid: config.mid,
                                mode: 'zin',
                                x: boundaries.x,
                                y: boundaries.y,
                                w: boundaries.w,
                                h: boundaries.h
                            },
                            success: that.handleSuccess,
                            error: that.handleError
                        });

                    // box action
                    } else if (select_box.context == 'select') {

                        if (!config.hasOwnProperty('box_action') || !config.hasOwnProperty('box_action_dlayers')) { return; }

                        that.loading.show();
                        jQuery.ajaxq(ajaxq_name, {
                            type: 'GET',
                            url: action_register[config.box_action].url,
                            dataType: 'json',
                            data: {
                                mid: config.mid,
                                action: config.box_action,
                                select_mode: config.select_mode,
                                x: boundaries.x,
                                y: boundaries.y,
                                w: boundaries.w,
                                h: boundaries.h,
                                dlayers: config.box_action_dlayers.join(',')
                            },
                            success: function(resp) {
                                action_register[config.box_action].callback(resp);
                                that.handleSuccess(resp);
                            },
                            error: that.handleError
                        });

                    }
                }
            };          

            /** @private */
            function testHover(event) {    
                var x = event.pageX - vp_pos.x;
                var y = event.pageY - vp_pos.y;
                var ma_pos = getCurrentMovingAnchorPos();
                var found = false;
                jQuery.each(hover_maps[history_idx], function(dlayer, list) {
                    jQuery.each(list, function(i, hi) {
                        // convert to viewport coord (relative to page itself)
                        var hx = hi.px + ma_pos.x; // !!! the +2 here is meant to correct some border 
                        var hy = hi.py + ma_pos.y; //     dimension issue that I'm not sure or (to verify)
                        // if in the vicinity of hover item, activate hover div
                        if (x > (hx - 5) && x < (hx + 5) && y > (hy - 5) && y < (hy + 5)) {
                            hover.html(hi.html);
                            hover.css({left: (x) + 10, top: (y)});
                            hover.show();
                            found = true;
                            return false; // break inner $.each
                        }
                    });
                    if (found) { return false; } // break outer $.each
                });
                if (!found) {
                    hover.hide();
                }
                return found;
            };

            ////////////////////
            // PUBLIC METHODS //
            ////////////////////

            /**
               Initial call to the Dracones server to register the map widget 
               and set everything up (in particular, sets up the session variable).
             */
            this.init = function() {

                init_completion_check_required = true;
                init_completion_check_passed = false;
                resetHoverMaps();

                that.loading.show();
                jQuery.ajaxq(ajaxq_name, {
                    type: 'GET',
                    url: dracones_url + '/dracones_do/init',
                    dataType: 'json',
                    data: {
                        app: config.app_name,
                        mid: config.mid,
                        map: config.map,
                        dlayers: config.init_dlayers.join(','),
                        mvpw: map_vp_width,
                        mvph: map_vp_height,
                        msvp: config.map_size_rel_to_vp,
                        history_size: config.history_size
                    },
                    success: that.handleSuccess,
                    error: that.handleError
                });
            };

            /** 
               Resets the map to its initial extent.
             */ 
            this.fullExtent = function() {
                that.loading.show();
                jQuery.ajaxq(ajaxq_name, {
                    type: 'GET',
                    url: dracones_url + '/dracones_do/fullExtent',
                    dataType: 'json',
                    data: {                        
                        mid: config.mid
                    },
                    success: that.handleSuccess,
                    error: that.handleError
                });
            };

            /**
               Callback used after the completion of every Dracones ajax request, to update the map widget.

               @param {JSON obj} resp The JSON response object.
             */
            this.handleSuccess = function(resp) {

                if (!resp.hasOwnProperty('success') || !resp.success) {
                    that.handleError(resp);
                    return;
                }

                hover.hide();
                setTimeout(function() {
                    that.point_zoom_marker.hide();
                }, 250);
                
                // map positioning (pan, etc.)
                pan_dir = null;
                if (resp.hasOwnProperty('pan_dir')) {
                    pan_dir = resp.pan_dir;
                }
                center_viewport = false;
                if (resp.hasOwnProperty('extent')) { // the viewport must be centered only if the extent has changed
                                                     // panning is special though, as it requires it own centering
                    if (!areExtentsEqual(resp.extent, curr_extent) && !resp.hasOwnProperty('pan_dir')) {
                        center_viewport = true;
                    }
                }
                var now = new Date().getTime(); // time is added to img.src to prevent caching
                getAlternateMovingAnchor().map_img.attr('src', resp.map_img_url + '?' + now);
                
                if (resp.shift_history_window && config.history_size >= 2) {

                    /*
                       # To preserve the forward order of the history items (i.e. an action at position i is "newer" than one at position < i),
                       # we need to detect the case where a new action is initiated somewhere in the history before then end (i.e. undo
                       # was used, once or more, and then a new action happened). This means that history_idx < history_size-1.
                       # The idea is that we will trim the "future part" of the history (i.e. the part to the right of history_idx) and 
                       # start from there.
                       # Example: a b c d e
                       # If we return back to element c, and issue new action f
                       # the outcome should be: _ a b c f
                       # Note that we must use a special "init" padding for the first element (_), to prevent going back to it.
                       # The same mechanism is also used in the server module.
                    */
                    
                    if (history_idx != (config.history_size - 1)) {
                        
                        var hover_maps_copy = jQuery.extend(true, [], hover_maps);
                        for (var i = 0; i < history_idx + 1; i++) {
                            var h = config.history_size - history_idx - 2 + i;
                            hover_maps[h] = jQuery.extend(true, {}, hover_maps_copy[i]); // deep copy
                        }
                        hover_maps[config.history_size - 1] = jQuery.extend(true, {}, hover_maps[config.history_size - 2]); // deep copy
                        
                    // If not, shift history leftward

                    } else {
                        
                        for (var i = 0; i < config.history_size; i++) {
                            var j = i < (config.history_size - 1) ? (i+1) : (i-1); // last element is doubled
                            hover_maps[i] = jQuery.extend(true, {}, hover_maps[j]); // deep copy
                        }
                        
                    }
                } 

                history_idx = resp.history_idx;

                if (resp.shift_history_window || config.history_size == 1) {

                    // new items 
                    if (resp.hasOwnProperty('hover')) {
                        jQuery.each(resp.hover, function(dlayer, dlayer_hi) {
                            if (!dlayer_hi.append || typeof hover_maps[history_idx][dlayer] === 'undefined') {
                                hover_maps[history_idx][dlayer] = [];
                            } 
                            jQuery.each(dlayer_hi.items, function(i, hi) {
                                var hi = { gx : parseFloat(hi[0]), gy : parseFloat(hi[1]), html : hi[2]};
                                hover_maps[history_idx][dlayer].push(hi);
                            });
                        });
                    }
                }

                if (resp.hasOwnProperty('extent')) {
                    curr_extent = resp.extent;
                    jQuery.each(hover_maps[history_idx], function(dlayer, list) {
                        jQuery.each(list, function(i, hi) {
                            var p = geo2pix(curr_extent, hi.gx, hi.gy, map_vp_width * config.map_size_rel_to_vp, map_vp_height * config.map_size_rel_to_vp);
                            hover_maps[history_idx][dlayer][i].px = p.x;
                            hover_maps[history_idx][dlayer][i].py = p.y;
                        });
                    });
                }

                // update undo/redo controls selected state 
                if (config.hasOwnProperty('undo_control_id')) {
                    jQuery('#' + config.undo_control_id).attr('disabled', !resp.can_undo);
                }
                if (config.hasOwnProperty('redo_control_id')) {
                    jQuery('#' + config.redo_control_id).attr('disabled', !resp.can_redo);
                }

                // See init_completion_check above
                if (init_completion_check_required) {
                    init_completion_check_required = false;
                    setTimeout(function() {
                        if (!init_completion_check_passed) {
                            var error_msg = 'It seems that the init call has not succeeded. ';
                            error_msg += 'One likely cause of that problem is that the Apache "Alias" directive for the "ms_tmp" directory has not been properly defined.';
                            error_msg += 'When properly set, you should be able to view the static map image that was just created by visiting:<br><br>';
                            error_msg += '<code><a href="' + resp.map_img_url + '>' + resp.map_img_url + '</a></code>';
                            that.handleError({responseText: error_msg});
                        }
                    }, 5000); // wait 5 seconds before triggering the test
                }

                if (that.success_callback) {
                    that.success_callback(resp);
                }
            };

            /** 
                Sets a callback which is called when handleSuccess (master map update function) is done.

                @param {function} fn The callback function, which is passed the whole "resp" object (coming from handleSuccess) as its only argument.
             */            
            this.setSuccessCallback = function(fn) {
                if (typeof fn === 'function') {
                    that.success_callback = fn;
                }
            };
            
            /** 
                Dracones ajax request error callback.

                @param {obj} resp If resp has a responseText property, will display it on screen, if not will display a list of properties.
             */            
            this.handleError = function(resp) {
                that.loading.hide();
                that.point_zoom_marker.hide();               
                if (resp.hasOwnProperty('error')) {
                    if (resp.error == 'not_initted' || resp.error == 'session_expired') {
                        that.init();
                        return;
                    }
                }
                var s = '<h2>Dracones Server Error:</h2>';
                if (resp.responseText) {
                    console.error(resp.responseText);
                    s += resp.responseText;
                } else {
                    for (k in resp) {
                        s += k + ': ' + resp[k] + '<br>';
                        console.error(k, ': ', resp[k]);
                    }
                }
                document.write(s);
                document.close();
            };

            /** 
                This particular MapWidget id. It must be passed to every Dracones ajax request.
                @type {str}
             */
            this.getMID = function() {
                return config.mid;
            };

            /**
                This is sometimes necessary with applications sporting a complex UI: the map widget viewport's absolute
                position can be recomputed after the whole UI is rendered, to update possibly wrong positioning values.
             */
            this.recomputeViewportAbsolutePos = function() {
                vp_pos = getAbsolutePosition(vp[0]);
            };
            
            /**
              Viewport horizontal and vertical displacement (resulting from panning) values, in pixels.
              @type {x:int, y:int}
             */
            this.getViewportTranslation = function() {
                var ma_pos = getCurrentMovingAnchorPos();
                return { x: (moving_anchor_base_pos.x - ma_pos.x),
                         y: (moving_anchor_base_pos.y - ma_pos.y) };
            };

            /**
                Toggles the status (on/off) of some dlayers.

               @param {obj} args An object containing the function parameters as properties.
                @param {str[]} args.dlayers List of DLayer names (single string element/name is allowed).
                @param {function} [args.callback] Callback triggered at completion (it is passed the JSON response from the server).
             */
            this.toggleDLayers = function(args) {
                if (typeof args.dlayers === 'string') {
                    args.dlayers = [args.dlayers];
                }
                that.loading.show();
                jQuery.ajaxq(ajaxq_name, {
                    type: 'GET',
                    url: dracones_url + '/dracones_do/toggleDLayers',
                    dataType: 'json',
                    data: {
                        mid: config.mid,
                        dlayers: args.dlayers.join(',')
                    },
                    success: function(r) {
                        that.handleSuccess(r);
                        if (args.hasOwnProperty('callback') && typeof args.callback === 'function') {
                            args.callback(r);
                        }
                    },
                    error: that.handleError
                });                
            };

            /**
                This sends a custom request to a Dracones enabled Python script.
 
                @param {obj} args An object containing the function parameters as properties.            
                @param {str} args.url The URL of the Python script + function.
                @param {obj} [args.data] The data/parameters to be sent to the script (if the MID is not present, it will be added).
                @param {function} [args.callback] Callback triggered at success completion (it is passed the JSON response from the server).
                @param {function} [args.success] Success replacement callback (you will need to manually handleSuccess though).
                @param {function} [args.error] Error replacement callback (you will need to manually handleSuccess though).
             */
            this.customRequest = function(args) { 
                if (!args.hasOwnProperty('data')) {
                    args.data = {mid: config.mid};
                } else if (!args.data.hasOwnProperty('mid')) {
                    args.data.mid = config.mid;
                }
                if (typeof args.success !== 'function') {
                    args.success = function(r) {
                        that.handleSuccess(r);
                        if (typeof args.callback === 'function') {
                            args.callback(r);
                        }
                    };
                }
                if (typeof args.error !== 'function') {
                    args.error = that.handleError;
                }
                // If found, remove first "/" from url, because it would prevent the 
                // RewriteRule to work correctly (PHP version)
                if (args.url[0] == '/') {
                    args.url = args.url.substring(1, args.url.length);
                }
                that.loading.show();
                jQuery.ajaxq(ajaxq_name, {
                    type: 'GET',
                    url: args.url,
                    dataType: 'json',
                    data: args.data,
                    success: args.success,
                    error: args.error
                });                
            };

            /**
                Registers a new action, or modifies the properties of an existing one.

                @param {obj} args An object containing the function parameters as properties.
                @param {str} args.name Name of the action.
                @param {str} [args.url] URL of the corresponding Python script + function.
                @param {function} [args.callback] Callback at completion (it is passed the JSON response from the server).
             */
            this.registerAction = function(args) {
                if (!action_register.hasOwnProperty(args.name)) {
                    action_register[args.name] = {}
                } 
                for (prop in args) {
                    action_register[args.name][prop] = args[prop];
                    if (prop == 'url') {
                        // If found, remove first "/" from url, because it would prevent the 
                        // RewriteRule to work correctly (PHP version)
                        if (action_register[args.name].url[0] == '/') {
                            action_register[args.name].url = action_register[args.name].url.substring(1, action_register[args.name].url.length);
                        }                        
                    }
                }
            };

            /**
                Set or modify the action modes, triggered by the mouse (holding CTRL + left button).

                @param {obj} args An object containing the function parameters as properties.
                @param {str} [args.point_action] A CTRL + single click action.
                @param {str[]} [args.point_action_dlayers] List of DLayers on which the point action must be performed (single item allowed).
                @param {str} [args.box_action] A CTRL + left drag action.
                @param {str[]} [args.box_action_dlayers] List of DLayers on which the box action must be performed (single item allowed).
             */
            this.setModeActions = function(args) {
                if (args.hasOwnProperty('point_action')) {
                    config.point_action = args.point_action;
                }
                if (args.hasOwnProperty('point_action_dlayers')) {
                    if (typeof args.point_action_dlayers === 'string') {
                        config.point_action_dlayers = [args.point_action_dlayers];
                    } else {
                        config.point_action_dlayers = args.point_action_dlayers;
                    }
                }
                if (args.hasOwnProperty('box_action')) {
                    config.box_action = args.box_action;
                }
                if (args.hasOwnProperty('box_action_dlayers')) {
                    if (typeof args.box_action_dlayers === 'string') {
                        config.box_action_dlayers = [args.box_action_dlayers];
                    } else {
                        config.box_action_dlayers = args.box_action_dlayers;
                    }
                }
            };

            /**
                Binds the map image export function to a UI control (eg. button).

                @param {str} control_id ID of a DOM element.            
             */
            this.bindExportImage = function(control_id) {
                jQuery('#' + control_id).click(function() {
                    var vpt = that.getViewportTranslation();
                    location.href = dracones.url + '/dracones_do/export?mid=' + config.mid + '&vptx=' + -vpt.x + '&vpty=' + -vpt.y;
                });
            };

            /**
                Performs undo/redo.

                @param {obj} args An object containing the function parameters as properties.
                @param {"undo"|"redo"} args.direction Which direction to go in history..
                @param {function} [args.callback] Callback triggered at completion (it is passed the JSON response from the server).
             */
            this.history = function(args) {
                that.loading.show();
                jQuery.ajaxq(ajaxq_name, {
                    type: 'GET',
                    url: dracones_url + '/dracones_do/history',
                    dataType: 'json',
                    data: {                        
                        mid: config.mid,
                        dir: args.direction
                    },
                    success: function(r) {
                        that.handleSuccess(r);
                        if (args.hasOwnProperty('callback') && typeof args.callback === 'function') {
                            args.callback(r, args.direction);
                        }
                    },
                    error: that.handleError
                });                
            };

            /**
                Clears list of dlayers of certain attributes.
 
                @param {obj} args An object containing the function parameters as properties.
                @param {str[]} args.dlayers List of dlayers to clear (single item allowed).
                @param {"all"|"selected"|"filtered"|"features"} args.what Type of items that will be cleared.
                @param {function} [args.callback] Callback triggered at completion (it is passed the JSON response from the server).
             */
            this.clearDLayers = function(args) {
                if (typeof args.dlayers === 'string') {
                    args.dlayers = [args.dlayers];
                }
                that.loading.show();
                jQuery.ajaxq(ajaxq_name, {
                    type: 'GET',
                    url: dracones_url + '/dracones_do/clearDLayers',
                    dataType: 'json',
                    data: {                        
                        mid: config.mid,
                        dlayers: args.dlayers.join(','),
                        what: args.hasOwnProperty('what') ? args.what : 'all'
                    },
                    success: function(r) {
                        that.handleSuccess(r);
                        if (args.hasOwnProperty('callback') && typeof args.callback === 'function') {
                            args.callback(r);
                        }
                    },
                    error: that.handleError
                });                                
            };

            /**
                Sets lists of dlayers status on/off.

                @param {obj} args An object containing the function parameters as properties.
                @param {str[]} [args.on] List of dlayers to show (single item allowed).
                @param {str[]} [args.off] List of dlayers to hide (single item allowed).
                @param {function} [args.callback] Callback triggered at completion (it is passed the JSON response from the server).
             */
            this.setDLayers = function(args) {
                var dlayers_on = [];
                var dlayers_off = [];
                if (args.hasOwnProperty('on')) {
                    dlayers_on = args.on;
                    if (typeof args.on === 'string') {
                        dlayers_on = [args.on];
                    } 
                }
                if (args.hasOwnProperty('off')) {
                    dlayers_off = args.off;
                    if (typeof args.off === 'string') {
                        dlayers_off = [args.off];
                    }
                }
                that.loading.show();
                jQuery.ajaxq(ajaxq_name, {
                    type: 'GET',
                    url: dracones_url + '/dracones_do/setDLayers',
                    dataType: 'json',
                    data: {                        
                        mid: config.mid,
                        dlayers_on: dlayers_on.join(','),
                        dlayers_off: dlayers_off.join(',')
                    },
                    success: function(r) {
                        that.handleSuccess(r);
                        if (args.hasOwnProperty('callback') && typeof callback === 'function') {
                            args.callback(r);
                        }
                    },
                    error: that.handleError
                });                                
            };

            /**
               Explicit definition of history widgets and behaviors.

               @param {obj} args An object containing the function parameters as properties.
               @param {str} [args.undo_control_id] The id of the undo control.
               @param {str} [args.redo_control_id] The id of the redo control.
               @param {function} [args.callback] Callback passed to history method (note that history() (hence this callback also) will not be called if args.prevent_click_binding is set to true).
               @param {bool} [args.prevent_click_binding] Set to true if for some reason you want to bind the history to something 
                                                          other than the click handler of the controls.
             */
            this.setHistoryControls = function(args) {
                var callback = null;
                if (args.hasOwnProperty('callback') && typeof args.callback === 'function') {
                    callback = args.callback;
                }
                if (args.hasOwnProperty('undo_control_id')) {
                    config.undo_control_id = args.undo_control_id;
                    if ((args.hasOwnProperty('prevent_click_binding') && !args.prevent_click_binding) || !args.hasOwnProperty('prevent_click_binding')) {
                        jQuery('#' + config.undo_control_id).click(function() {
                            that.history({direction: 'undo', callback: callback});
                        });
                    }
                }
                if (args.hasOwnProperty('redo_control_id')) {
                    config.redo_control_id = args.redo_control_id;
                    if ((args.hasOwnProperty('prevent_click_binding') && !args.prevent_click_binding) || !args.hasOwnProperty('prevent_click_binding')) {
                        jQuery('#' + config.redo_control_id).click(function() {
                            that.history({direction: 'redo', callback: callback});
                        });
                    }
                }
            };

            /**
               Selection of a set of map features.

               @param {obj} args An object containing the function parameters as properties.
               @param {str} args.dlayer DLayer on which to perform the selection.
               @param {str[]} args.features Feature IDs to select (single item allowed).
               @param {str} [args.select_mode] Temporary selection mode ("reset", "toggle" or "add") override
                                               (does not modify the global selection mode).
             */
            this.selectFeatures = function(args) {
                if (typeof args.features !== 'object') {
                    args.features = [args.features];
                }
                that.loading.show();
                jQuery.ajaxq(ajaxq_name, {
                    type: 'GET',
                    url: dracones_url + '/dracones_do/selectFeatures',
                    dataType: 'json',
                    data: {                        
                        mid: config.mid,
                        dlayer: args.dlayer,
                        features: args.features.join(','),
                        select_mode: args.hasOwnProperty('select_mode') ? args.select_mode : config.select_mode
                    },
                    success: that.handleSuccess,
                    error: that.handleError                    
                });                                
            };

            /**
               Show/hide features.

               @param {obj} args An object containing the function parameters as properties.
               @param {str} args.dlayer Target DLayer.
               @param {str[]} args.features Feature IDs (single item allowed).               
               @param {bool[]} args.visibles Feature visibility statuses (single item allowed).
             */
            this.setFeatureVisibility = function(args) {
                if (typeof args.features !== 'object') {
                    args.features = [args.features];
                }
                if (typeof args.visibles !== 'object') {
                    args.visibles = [args.visibles];
                }
                that.loading.show();
                jQuery.ajaxq(ajaxq_name, {
                    type: 'GET',
                    url: dracones_url + '/dracones_do/setFeatureVisibility',
                    dataType: 'json',
                    data: {                        
                        mid: config.mid,
                        dlayer: args.dlayer,
                        features: args.features.join(','),
                        visibles: args.visibles.join(',')
                    },
                    success: that.handleSuccess,
                    error: that.handleError                    
                });                                
            };

            // If delayed init is not set, trigger init.
            if (!config.hasOwnProperty('delayed_init') || !config.delayed_init) {
                that.init();
            }

        } // end DraconesMap definition

    } // end dracones module public part

})(); // end dracones module definition/instantiation
