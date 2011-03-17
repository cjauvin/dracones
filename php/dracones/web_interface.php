<?php

/*!
  @defgroup web_interface
  Dracones client/server communication module: basically, all the client
  services have their binding here. It also serves as the basis for
  Dracones extension functions, that get structured with sequential
  calls to beginDracones, endDracones and exitDracones.

  Every web-accessible function/service in this module is structured as follow:

<pre>
function foo():

    $arr = beginDracones();
    $params = $arr[0]; $dmap = $arr[1];

    # Code to perform operations on the dmap, probably using the params..

    $json_out = endDracones($dmap);

    # Put any required additional information in json_out..

    return exitDracones($json_out);
</pre>
*/

require_once('php/dracones/core.php');

@session_start();

/*!  
  @ingroup web_interface 
  This function is specific to the PHP version of Dracones. It serves as a main 
  entry point for the script where it is being executed: it checks the content 
  of the "do" GET variable (passed as part of the RewriteRule redirection) 
  against a list of registered (exposed) services available in the current script. 
  Upon finding one, it simply executes the corresponding function.

  @param registered_services The list of exposed services for the current script 
                             (tolerates single element instead of list).
 */
function doDracones($registered_services) {
    
    if (!is_array($registered_services)) { 
        $registered_services = array($registered_services); 
    }
    if (in_array($_REQUEST['do'], $registered_services)) {
        $_REQUEST['do']();
    }

}

doDracones(array('init', 'pan', 'zoom', 'fullExtent', 'action', 'setDLayersStatus', 'clearDLayers',
                 'toggleDLayers', 'export', 'setFeatureVisibility', 'selectFeatures', 'history'));


/*!
  @ingroup web_interface
  First step of any Dracones complete interaction: session
  checking, parameter extraction, dmap creation and state
  restoration.

  @param kw An array to emulate keyword arguments.
  @param restore_extent If False, the extent will be the map's default.
  @param add_features Whether to wait before adding the features: some feature manipulations (selection, clear) must be
                       performed prior this call, so it can be deferred (and must be called manually later).
  @param use_viewport_geom Only used for map image export.
  @param history_dir Undo/redo.
  @return ($params, $dmap) array, on which to perform custom operations at will.
*/
function beginDracones($kw = array()) {   

    $restore_extent = get($kw, 'restore_extent', True);
    $add_features = get($kw, 'add_features', True);
    $use_viewport_geom = get($kw, 'use_viewport_geom', False);
    $history_dir = get($kw, 'history_dir', null);

    $params = $_REQUEST;
    $sess = &$_SESSION;

    $mid = $params['mid'];

    if (!isset($sess[$mid])) {
        die(json_encode(array('success'=> False, 'error'=> 'session_expired',
                              'error_msg'=> 'Session has expired')));
    }
    
    if ($history_dir == 'undo') {
        assert($sess[$mid]['history_idx'] > 0);
        $sess[$mid]['history_idx']--;    
    } else if ($history_dir == 'redo') {
        assert($sess[$mid]['history_idx'] < $sess[$mid]['history_size'] - 1);
        $sess[$mid]['history_idx']++;
    }
    
    $dmap = new DMap($mid, $use_viewport_geom);
    $dmap->restoreStateFromSession($restore_extent);
    if ($add_features) {
        $dmap->addDLayerFeatures();
    }
    
    return array($params, $dmap);

}

/*!
  @ingroup web_interface
  Second step of any Dracones complete interaction: creation of
  the return JSON object containing all the variables required
  by the client, state save in the session.
  
  @param dmap The dmap returned by the previous call to beginDracones.
  @param shift_history_window If an operation is not to be recorded in the session, the history window must not be shifted.
  @param update_session Whether to update the session or not (for instance, when going back/forward in the history, this is needed).
  @return json_out JSON dict, containing all the variables required by the client, and that can be modified
          between the return of this call and the final call to exitDracones.
*/
function endDracones($dmap, $kw = array()) {

    $sess = &$_SESSION;

    $shift_history_window = get($kw, 'shift_history_window', True);
    $update_session = get($kw, 'update_session', True);

    $json_out = array('success' => True);
    $json_out['extent'] = $dmap->getExtent();
    $json_out['hover'] = $dmap->getHoverItems();
    $json_out['selection'] = $dmap->getSelection();
    $json_out['map_img_url'] = $dmap->getImageURL();
    if ($update_session) {
        $dmap->saveStateInSession($shift_history_window);
    }
    $json_out['can_undo'] = $sess[$dmap->mid]['history_idx'] > 0 && (!in_array('init', $sess[$dmap->mid]['history'][$sess[$dmap->mid]['history_idx']-1]));
    $json_out['can_redo'] = $sess[$dmap->mid]['history_idx'] < ($sess[$dmap->mid]['history_size'] - 1);
    $json_out['history_idx'] = $sess[$dmap->mid]['history_idx'];
    $json_out['shift_history_window'] = $update_session ? $shift_history_window : False;
    return $json_out;

}

/*!
  @ingroup web_interface
  Last step of any Dracones complete interaction: the response
  sent back to the client.  This function is decoupled for the
  only purpose of letting custom code add some stuff to the
  json_out variable, returned by the previous call to
  endDracones, before it gets returned.

  @param json_out The json_out map returned by the previous call to endDracones, and possibly modified by custom code.
 */
function exitDracones($json_out) {

    die(json_encode($json_out));
    return True;

}

/*!
  @ingroup web_interface
  Mandatory first client call: sets up the session object, with all the required parameters.

  @param app_name HTTP GET param - name of the application.
  @param mid HTTP GET param - map widget instance; useful if more than one widgets for the same app.
  @param mvpw HTTP GET param - map viewport width (corresponds to the widget div dimensions; underlying map will be bigger than that, see msvp param).
  @param mvph HTTP GET param - map viewport height (corresponds to the widget div dimensions; underlying map will be bigger than that, see msvp param).
  @param msvp HTTP GET param - map size relative to the viewport (the viewport dims will be multiplied by this value).
  @param history_size HTTP GET param - number of history cells kept (nb. of times undo will be allowed, in other words).
*/
function init() {

    $params = $_REQUEST;
    $sess = &$_SESSION;
    $json_out = array('success' => True);

    // init params
    $app_name = get($params, 'app', null);
    $mid = get($params, 'mid', null);
    $map_name = get($params, 'map', null);
    $mvpw = (int)get($params, 'mvpw', 0); // map viewport width
    $mvph = (int)get($params, 'mvph', 0); // map viewport height
    $msvp = (int)get($params, 'msvp', 0); // map size relative to viewport
    $history_size = (int)get($params, 'history_size', 0);

    if (!$app_name || !$mid || !$map_name || !$mvpw || !$mvph || !$msvp) {
        die(json_encode(array('success' => False, 'error' => 'missing init variables (app, mid, map, mvpw, mvph, msvp)')));
    }

    $sess[$mid] = array('app' => $app_name, 'map' => $map_name, 'mvpw' => $mvpw, 'mvph' => $mvph, 'msvp' => $msvp, 
                        'history_size' => $history_size, 'history' => array(), 'history_idx' => ($history_size - 1) );

    for ($i = 0; $i < $history_size; $i++) {
        $hist_cell = newHistoryCell();
        if ($i < ($history_size - 1)) {
            $hist_cell['init'] = True; // special markers to make it impossible to go back to these 
        }
        $sess[$mid]['history'][] = $hist_cell;
    }

    $dmap = new DMap($mid);

    return exitDracones(endDracones($dmap, array('shift_history_window'=>False)));
            
}

/*!
  @ingroup web_interface
  Reset the map initial extent.
*/
function fullExtent() {

    $arr = beginDracones(array('restore_extent' => False));
    $params = $arr[0]; $dmap = $arr[1];
    return exitDracones(endDracones($dmap));

}

/*!
  @ingroup web_interface
  Pan map in one of four directions.

  @param pan_dir HTTP GET param - the direction in which to pan the map.
*/
function pan() {    

    $arr = beginDracones();
    $params = $arr[0]; $dmap = $arr[1];
    $pan_dir = $params['dir'];
    $dmap->pan($pan_dir);
    $json_out = endDracones($dmap, array('shift_history_window' => True));
    $json_out['pan_dir'] = $pan_dir;
    return exitDracones($json_out);

}

/*!
  @ingroup web_interface
  Point/box zoom.
  
  @param x HTTP GET param - x coord (in pixel/map coords).
  @param y HTTP GET param - y coord (in pixel/map coords).
  @param w HTTP GET param - width of the box zoom (optional, in map pixels).
  @param h HTTP GET param - height of the box zoom (optional, in map pixels).
  @param mode HTTP GET param - zoom mode, "in" or "out".
  @param zsize HTTP GET param - zoom size.
*/
function zoom() {

    $arr = beginDracones();
    $params = $arr[0]; $dmap = $arr[1];

    $x = (int)$params['x'];
    $y = (int)$params['y'];
    $w = (int)get($params, 'w', 0);
    $h = (int)get($params, 'h', 0);
    $mode = get($params, 'mode', null);
    $zsize = (int)get($params, 'zsize', 2);

    $dmap->zoom($x, $y, $w, $h, $mode, $zsize);

    return exitDracones(endDracones($dmap));    

}

/*!
  @ingroup web_interface
  An action is triggered by the use of CTRL + left mouse
  button: a I{point action} for CTRL + single click, and a I{box
  action} for CTRL + drag. This function can only perform two
  default Dracones actions: select and draw. You can point/box
  select items on multiple layers at once, provided that they have
  CLASSITEM attributes. You can also draw a feature at a particular
  x/y location. B{Note that for the moment, the drawing of an object
  with rectangular coordinates is not supported.}

  @param x HTTP GET param - x coord (in pixel/map coords).
  @param y HTTP GET param - y coord (in pixel/map coords).
  @param w HTTP GET param - width of the box zoom (optional, in map pixels).
  @param h HTTP GET param - height of the box zoom (optional, in map pixels).
  @param action HTTP GET param - the action to perform.
  @param select_mode HTTP GET param - how selection is to be performed on a DLayer: "reset" (default) will unselect all features before selecting new ones, 
                                     "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
  @param dlayers HTTP GET param - list of dlayers on which to perform the action.
*/
function action() {
   
    $arr = beginDracones(array('add_features' => False));
    $params = $arr[0]; $dmap = $arr[1];

    $x = (int)$params['x'];
    $y = (int)$params['y'];
    $w = (int)get($params, 'w', 0);
    $h = (int)get($params, 'h', 0);
    $action = get($params, 'action', null);
    $select_mode = get($params, 'select_mode', 'reset');
    $dlayers = get($params, 'dlayers', null);

    if ($action == 'select') {

        // only significant for custom feature layers
        if ($select_mode == 'reset') {
            foreach (explode(',', $dlayers) as $dlayer_name) {
                $dmap->clearDLayer($dlayer_name, 'selected');
            }
        }

        $dmap->addDLayerFeatures();
        $dmap->select(explode(',', $dlayers), $x, $y, $w, $h, $select_mode);

    } else if ($action == 'draw') {

        $dmap->addDLayerFeatures();
        foreach (explode(',', $dlayers) as $dlayer_name) {
            if ($dmap->hasDLayer($dlayer_name)) {
                $dmap->dlayers[$dlayer_name]->drawFeature($x, $y);
            }
        }
        
    } else {

        assert(False);

    }

    return exitDracones(endDracones($dmap));    

}

/*!
  @ingroup web_interface
  Set dlayers status on/off.

  @param dlayers_on HTTP GET param - list of dlayers to activate.
  @param dlayers_off HTTP GET param - list of dlayers to desactivate.
*/
function setDLayersStatus() {

    $arr = beginDracones();
    $params = $arr[0]; $dmap = $arr[1];    

    $dlayers_on = get($params, 'dlayers_on', Null);
    $dlayers_off = get($params, 'dlayers_off', Null);
   
    foreach (explode(',', $dlayers_on) as $dlayer_name) {
        if (!$dmap->hasDLayer($dlayer_name)) {
            $dmap->setDLayer(createDLayerInstance($dlayer_name, $dmap));
        }
        $dmap->dlayers[$dlayer_name]->setStatus(MS_ON);
    }

    foreach (explode(',', $dlayers_off) as $dlayer_name) {
        if ($dmap->hasDLayer($dlayer_name)) {
            $dmap->dlayers[$dlayer_name]->setStatus(MS_OFF);
        }
    }

    return exitDracones(endDracones($dmap));

}

/*!
  @ingroup web_interface
  Clears dlayers with respect to certain attributes: selected/filtered items,
  features, all.
  
  @param what HTTP GET param - the items to clear.
  @param dlayers HTTP GET param - list of dlayers on which to apply the clear.
*/
function clearDLayers() {

    $arr = beginDracones(array('add_features' => False));
    $params = $arr[0]; $dmap = $arr[1];    

    $what = $params['what'];
    $dlayers_to_clear = get($params, 'dlayers', Null);

    foreach (explode(',', $dlayers_to_clear) as $dlayer_name) {
        $dmap->clearDLayer($dlayer_name, $what);
    }
    $dmap->addDLayerFeatures();

    return exitDracones(endDracones($dmap));

}

/*!
  @ingroup web_interface
  Toggle on/off list of dlayers.

  @param dlayers HTTP GET param - list of dlayers to toggle.
*/
function toggleDLayers() {

    $arr = beginDracones();
    $params = $arr[0]; $dmap = $arr[1];    

    $dlayers_to_toggle = get($params, 'dlayers', Null);

    foreach (explode(',', $dlayers_to_toggle) as $dlayer_name) {
        if ($dmap->dlayers[$dlayer_name]->getStatus() == MS_ON) {
            $dmap->dlayers[$dlayer_name]->setStatus(MS_OFF);
        } else {
            $dmap->dlayers[$dlayer_name]->setStatus(MS_ON);
        }
    }

    return exitDracones(endDracones($dmap));

}

/*!
  @ingroup web_interface
  Export an image of the current map.
  
  @param vptx HTTP GET param - viewport horizontal translation, in map/pixel coords.
  @param vpty HTTP GET param - viewport vertical translation, in map/pixel coords.
*/
function export() {

    global $dconf;

    $arr = beginDracones(array('use_viewport_geom' => True));
    $params = $arr[0]; $dmap = $arr[1];

    $sess = &$_SESSION;

    // input params
    $vptx = get($params, 'vptx', 0);
    $vpty = get($params, 'vpty', 0);

    $hist_idx = $sess[$dmap->mid]['history_idx'];
    $xt = $sess[$dmap->mid]['history'][$hist_idx]['extent'];

    // First adjust temp extent to match vp size map
    $xvp = ($xt['maxx'] - $xt['minx']) / $sess[$dmap->mid]['msvp'];
    $yvp = ($xt['maxy'] - $xt['miny']) / $sess[$dmap->mid]['msvp'];
    $hnvp = ($sess[$dmap->mid]['msvp'] - 1) / 2; // half n viewports
    $xt['minx'] += ($hnvp * $xvp);
    $xt['maxx'] = $xt['minx'] + $xvp;
    $xt['miny'] += ($hnvp * $yvp);
    $xt['maxy'] = $xt['miny'] + $yvp;
    $dmap->setExtentFromDict($xt);

    // Then adjust for viewport translation
    $disp_geo = pix2geo($dmap->ms_map, $vptx, $vpty);
    $xd = $xt['minx'] - $disp_geo->x;
    $yd = $xt['maxy'] - $disp_geo->y;
    $xt['minx'] += $xd;
    $xt['maxx'] += $xd;
    $xt['miny'] += $yd;
    $xt['maxy'] += $yd;
    $dmap->setExtentFromDict($xt);

    $img = $dmap->ms_map->draw();
    $img->imagepath = $dconf['ms_tmp_path'];
    // image filename structure: <mapname>_<mid>_<session_id>_EXPORT.<img_type>
    $fn = sprintf("%s_%s_%s_%s.%s", $sess[$dmap->mid]['map'], $dmap->mid, session_id(), "EXPORT", $dmap->ms_map->imagetype);
    $img_path = sprintf("%s%s%s", $dconf['ms_tmp_path'], ($dconf['ms_tmp_path'][strlen($dconf['ms_tmp_path'])-1] == '/' ? '' : '/'), $fn);
    $img->saveImage($img_path);

    $external_fn = sprintf("%s_%s.%s", $dmap->app_name, strftime('%Y-%m-%d_%Hh%Mm%Ss'), $dmap->ms_map->imagetype);

    header("Content-Type: application/octet-stream");
    header(sprintf('Content-Disposition: attachment; filename="%s"', $external_fn));
    ob_clean();
    flush();
    readfile($img_path);

}

/*!
  @ingroup web_interface
  Modifies the visibility status of a single feature item.

  @param dlayer HTTP GET param - the target dlayer.
  @param features HTTP GET param - the feature IDs to select.
  @param visibles HTTP GET param - visibility status corresponding to each feature.
  @param is_visible HTTP GET param - feature visibility status.
*/
function setFeatureVisibility() {

    $arr = beginDracones(array('add_features' => False));
    $params = $arr[0]; $dmap = $arr[1];    

    $dlayer_name = get($params, 'dlayer');
    $features = explode(',', get($params, 'features', ''));
    $visibles = explode(',', get($params, 'visibles', ''));

    assert(count($features) == count($visibles));

    for ($i = 0; $i < count($features); $i++) {
        $dmap->dlayers[$dlayer_name]->setFeatureVisibility($features[$i], (strtolower($visibles[$i])=='true'));
    }

    $dmap->addDLayerFeatures();

    return exitDracones(endDracones($dmap));

}

/*!
  @ingroup web_interface
  Select feature items.

  @param dlayer HTTP GET param - the targer dlayer.
  @param features HTTP GET param - the feature IDs to select.
  @param select_mode HTTP GET param - how selection is to be performed on a DLayer: "reset" (default) will unselect all features before selecting new ones, 
                                     "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
*/
function selectFeatures() {

    $arr = beginDracones(array('add_features' => False));
    $params = $arr[0]; $dmap = $arr[1];    

    $dlayer_name = get($params, 'dlayer');   
    $features = explode(',', get($params, 'features', ''));

    $select_mode = get($params, 'select_mode', 'reset');

    $dmap->selectFeatures($dlayer_name, $features, $select_mode);

    $dmap->addDLayerFeatures();

    return exitDracones(endDracones($dmap));

}

/*!
  @ingroup web_interface
  Navigate the map history (undo/redo).

  @param direction HTTP GET param - undo or redo.
*/
function history() {

    $direction = $_REQUEST['dir'];
    $arr = beginDracones(array('history_dir' => $direction));
    return exitDracones(endDracones($arr[1], array('update_session' => False)));

}

?>