<?php 

/*!
  @mainpage Dracones-PHP API
  @version 1.1.3
 */

/*!
  @defgroup core

  Main Dracones components and logic.
*/

require_once('php/dracones/conf.php');

function get($arr, $key, $default = Null) {
    if (array_key_exists($key, $arr)) {
        return $arr[$key];
    } else {
        return $default;
    }
}

// Taken from: http://www.php.net/manual/en/ref.array.php#81081
function array_deep_copy($src) {
    $src_copy = array();
    $keys = array_keys($src);
    $vals = array_values($src);        
    for ($i = 0; $i < count($keys); $i++) {
        // clone if object
        if (is_object($vals[$i])) {
            $src_copy[$keys[$i]] = clone $vals[$i];
        // recurse if array
        } else if (is_array($vals[$i])) {
            $src_copy[$keys[$i]] = array_deep_copy($vals[$i]);
        // value
        } else {
            $src_copy[$keys[$i]] = $vals[$i];
        }
    }
    return $src_copy;
}

/*!
  @ingroup core
  Pixel to geographical coordinates conversion.
  
  @param m The map object from which the extent will be extracted.
  @param px x coord in pixel value.
  @param py y coord in pixel value.
  @return A MS PointObj, with x and y properties.
*/
function pix2geo($m, $px, $py) {

    $dx = $m->extent->maxx - $m->extent->minx;
    $dy = $m->extent->maxy - $m->extent->miny;
    $dxpp = $dx / $m->width;
    $dypp = $dy / $m->height;
    $geox = $m->extent->minx + ($dxpp * $px);
    $geoy = $m->extent->maxy - ($dypp * $py);
    $p = ms_newpointObj();
    $p->setXY($geox, $geoy);
    return $p;

}

/*!
  @ingroup core
  Geographical to pixel coordinates conversion.

  @param m A MS MapObj instance (not a DMap!) from which the extent will be extracted.
  @param gx x coord in geo value.
  @param gy y coord in geo value.
  @return A (px, py) float tuple.
*/
function geo2pix($m, $gx, $gy) {

    function _geo2pix($geo_pos, $pix_min, $pix_max, $geo_min, $geo_max, $inv) {

        $w_geo = abs($geo_max - $geo_min);
        $w_pix = abs($pix_max - $pix_min);
        if ($w_geo <= 0) { return 0; }
        $g2p = $w_pix / $w_geo;
        if ($inv) {
            $del_geo = $geo_max - $geo_pos;
        } else {
            $del_geo = $geo_pos - $geo_min;
        }
        $del_pix = $del_geo * $g2p;
        $pos_pix = $pix_min + $del_pix;
        return (int)$pos_pix;

    }

    $px = _geo2pix($gx, 0, $m->width, $m->extent->minx, $m->extent->maxx, False);
    $py = _geo2pix($gy, 0, $m->height, $m->extent->miny, $m->extent->maxy, True);
    return array($px, $py);

}

/*!
  @ingroup core
  MS RectObj to assoc array. Is used in particular for map extent.

  @param r A MS RectObj object.
  @return array(minx=>.., miny=>.., maxx=>.., maxy=>..).
*/
function rectObjToDict($r) {
    return array('minx' => $r->minx, 'miny' => $r->miny, 'maxx' => $r->maxx, 'maxy' => $r->maxy);
}

/*!
  @ingroup core
  Creates an HistoryCell to store in the session variable.
  
  @return array(dlayers=>.., extent=>..).
*/
function newHistoryCell() {
    return array('dlayers' => array(), 'extent' => null);
}

/*!
  @ingroup core
  Instantiation of the proper subclass of DLayer, based on the layer type (a mapping from
  MS layer type to DLayer type).
  
  @param name Name of the layer.
  @param dmap The DMap containing the layer.
  @return An instance of a subclassed DLayer, according to the MS type of the layer.
*/
function createDLayerInstance($name, $dmap) {
    assert(!is_null($dmap->ms_map->getLayerByName($name)));
    $layer_type = $dmap->ms_map->getLayerByName($name)->type;
    if ($layer_type == MS_LAYER_POINT) {
        return new PointDLayer($name, $dmap);
    } else if ($layer_type == MS_LAYER_POLYGON) {
        return new PolygonDLayer($name, $dmap);        
    } else if ($layer_type == MS_LAYER_CIRCLE) {
        return new CircleDLayer($name, $dmap);                
    } else if ($layer_type == MS_LAYER_LINE) {
        return new LineDLayer($name, $dmap);                
    } else {
        return DLayer($name, $dmap);
    }
}

/*!
  @ingroup core
  Dracones encapsulation of a MS layer object.
*/
class DLayer {
    
    public $name;
    public $dmap;
    public $ms_layer;
    public $selected;
    public $is_filtered;
    public $filtered;
    public $features;
    public $hover_items;
    public $hover_items_are_dirty;
    public $hover_items_in_append_mode;
    public $group;
    public $shape_index;
    public $is_shapefile;

    /*!
      DLayer constructor.

      @param name Name of the layer (must correspond to an existing MS layer).
      @param dmap The DMap object containing the layer.        
     */
    function __construct($name, $dmap) {

        global $dconf;
        $this->name = $name;
        $this->dmap = $dmap;
        $this->ms_layer = $dmap->ms_map->getLayerByName($name);
        $this->selected = array();
        $this->is_filtered = $this->ms_layer->filteritem != '';
        $this->filtered = array();
        $this->features = array();
        $this->hover_items = array();
        $this->hover_items_are_dirty = False;
        $this->hover_items_in_append_mode = False;
        $this->group = $this->ms_layer->group;
        $this->shape_index = 0;
        $this->is_shapefile = False;
        if ($this->ms_layer->data) {
            $this->is_shapefile = !preg_match('/.* * from *.*/i', $this->ms_layer->data);
        }
        $this->select_item = null;
        if ($this->is_filtered) {
            $this->select_item = $this->ms_layer->filteritem;
        } else {
            $this->select_item = $this->ms_layer->classitem;
        }
        if ($this->ms_layer->connectiontype == MS_POSTGIS && !$this->ms_layer->connection) {
            if (get(get($dconf[$dmap->app_name], 'map', array()), 'postgis_connection', null)) {
                $this->ms_layer->set('connection', $dconf[$dmap->app_name]['map']['postgis_connection']);
            }
        }

    }

    /*!
      This performs mapscript.queryByAttributes on the underlying MS
      layer (resulting in a setFilter operation) and it also builds
      the set of corresponding hover items, using the desired fields
      in the supplied HTML template. Note that a 'select_item' must
      be defined within this DLayer (this corresponds to a CLASSITEM
      or FILTERITEM clause in the MS layer).
      
      @param attr The name of the queried attribute.
      @param value Value of the queried attribute.
      @param hover_item_html_template An HTML-based field name matching template for the hovering mechanism, used by the client.
                                      The string "<b>{name} {age}</b>" could result for instance in "<b>Bob 51</b>".
    */
    function queryByAttributes($attr, $value, $hover_item_html_template = "") {

        assert(!is_null($this->select_item));
        if (!is_array($value)) {
            $value = array($value);
        }

        if ($this->is_shapefile) {
            $arr = array();
            foreach ($value as $v) { $arr[] = sprintf('^%s$', $v); }
            $value_expr = sprintf("/%s/", implode("|", $arr));
        } else {
            $arr = array();
            foreach ($value as $v) { $arr[] = sprintf("'s'", $v); }
            $value_expr = sprintf("%s in (%s)", $attr, implode(",", $arr));
        }
        $filtered = array();
        $hover_items = array();
        $hover_item_html_tmpl_fields = array();
        if ($hover_item_html_template) {
            preg_match_all('/{(\w+)}/', $hover_item_html_template, $hover_item_html_tmpl_fields);
            if ($hover_item_html_tmpl_fields) {
                $hover_item_html_tmpl_fields = $hover_item_html_tmpl_fields[1];
            }
        }
        for ($i = 0; $i < count($hover_item_html_tmpl_fields); $i++) {
            $hover_item_html_tmpl_fields[$i] = strtolower($hover_item_html_tmpl_fields[$i]);
        }
        $succ = @$this->ms_layer->queryByAttributes($attr, $value_expr, MS_MULTIPLE);
        if ($succ == MS_SUCCESS) {
            $n_res = $this->ms_layer->getNumResults();
            for ($i = 0; $i < $n_res; $i++) {
                $res = $this->ms_layer->getResult($i);
                $shp = $this->ms_layer->resultsGetShape($res->shapeindex, $res->tileindex);
                $wkt = $shp->toWKT();

                $hover_item = array('gx'=>Null, 'gy'=>Null, 'html'=>Null);
                $hover_item_map = array();

                $m = array();
                preg_match('/POINT *[(](.*) (.*)[)]/', $wkt, $m);
                if ($m) {
                    $hover_item['gx'] = $m[1];
                    $hover_item['gy'] = $m[2];
                }

                $key_val = Null;

                foreach ($shp->values as $attr => $val) {

                    $attr = strtolower($attr);

                    if ($attr == strtolower($this->select_item)) {
                        $key_val = $val;
                    }

                    if (in_array($attr, $hover_item_html_tmpl_fields)) {
                        $hover_item_map[$attr] = $val;
                    }

                }

                if ($key_val) {

                    $hover_item_html = $hover_item_html_template;
                    foreach ($hover_item_html_tmpl_fields as $f) {
                        $hover_item_html = str_replace(sprintf("{%s}", $f), get($hover_item_map, $f, '?'), $hover_item_html);
                    }
                    $hover_item['html'] = $hover_item_html;

                    $filtered[] = $key_val;
                    $hover_items[] = $hover_item;
                }

            }
        }

        if ($this->is_filtered) {
            $this->setFilter($filtered);
        }
        $this->setHoverItems($hover_items);

    }

    /*!
      Retrieves all the attributes for a record identified by a pair attribute/value.
      
      @param attr Name of the key attribute.
      @param value Value of the key attribute.
      @return An attribute=>value array.
    */
    function getRecordAttributes($attr, $value) {

        assert(!is_null($this->select_item));
        if ($this->is_shapefile) {
            $value_expr = sprintf("/^%s$/", $value);
        } else {
            $value_expr = sprintf("%s = '%s'", $attr, $value);
        }
        $attributes = array();
        $succ = $this->ms_layer->queryByAttributes($attr, $value_expr, MS_SINGLE);
        if ($succ == MS_SUCCESS) {
            $res = $this->ms_layer->getResult(0);
            $shp = $this->ms_layer->resultsGetShape($res->shapeindex, $res->tileindex);
            return $shp->values;
        } else {
            return array();
        }

    }

    /*!
      Restore the state of the DLayer: filter, select, features, status.

      @param already_filtered List of filtered item IDs.
      @param already_selected List of selected item IDs.
      @param existing_features Dict of feature attributes (identified by id).
      @param status On/off status of the DLayer.
    */
    function restoreState($already_filtered, $already_selected, $existing_features, $status) {

        if ($this->is_filtered) {
            $this->setFilter($already_filtered);            
        }
        $this->setExpression($already_selected);
        $this->selected = $already_selected;
        $this->filtered = $already_filtered;
        $this->features = $existing_features;
        $this->setStatus($status);

    }

    /*!
      Will select item at point, using
      mapscript.layerObj.queryByPoint. If the dlayer has a
      select_item defined (CLASSITEM or FILTERITEM), it will build
      an MS expression, to be applied on the first class of the
      layer (if there are at least two; if not, the selection has no
      visual effect).  If not, it will modify directly the
      classindex of the selected feature (if any).
      
      @param p Selection MS PointObj, in geographic (not pixel/map) coordinates.
      @param select_mode How selection is to be performed: "reset" (default) will unselect all features before selecting new ones, 
                        "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
    */
    function pointSelect($p, $select_mode) {

        if ($this->select_item) {

            $succ = @$this->ms_layer->queryByPoint($p, MS_SINGLE, -1);
            if ($select_mode == 'reset') {
                $elements = array();
            } else {
                $elements = $this->selected;
            }
            if ($succ == MS_SUCCESS) {
                $res = $this->ms_layer->getResult(0);
                $shp = $this->ms_layer->resultsGetShape($res->shapeindex, $res->tileindex);
                $val = $shp->getValue($this->ms_layer, $this->select_item);
                if ($select_mode == 'reset' || $select_mode == 'add') {
                    $elements[] = $val;
                } else if ($select_mode == 'toggle') {
                    $key = array_search($val, $elements);
                    if ($key !== false) {
                        unset($elements[$key]);
                    } else {
                        $elements[] = $val;
                    }
                }
            }
            $this->setExpression($elements);

        } else if ($this->features) {

            $succ = @$this->ms_layer->queryByPoint($p, MS_SINGLE, -1);
            if ($succ == MS_SUCCESS) {
                $res = $this->ms_layer->getResult(0);
                $shp = $this->ms_layer->resultsGetShape($res->shapeindex, $res->tileindex);
                if ($select_mode == 'reset' || $select_mode == 'add') {
                    if (!in_array($res->shapeindex, $this->selected)) {
                        $this->selected[] = $res->shapeindex;
                        $shp->set('classindex', 1);
                    }       
                } else if ($select_mode == 'toggle') {
                    $key = array_search($res->shapeindex, $this->selected);
                    if ($key !== false) {
                        unset($this->selected[$key]);
                        $shp->set('classindex', 0);
                    } else {
                        $this->selected[] = $res->shapeindex;
                        $shp->set('classindex', 1);
                    }                        
                }
                $this->ms_layer->addFeature($shp);
            }
        }

    }

    /*!
      Will select item in a rectangle, using
      mapscript.layerObj.queryByRect. If the dlayer has a
      select_item defined (CLASSITEM or FILTERITEM), it will build
      an MS expression, to be applied on the first class of the
      layer (if there are at least two; if not, the selection has no
      visual effect).  If not, it will modify directly the
      classindex of the selected features (if any).

      @param g1 Rect top-left point, in geographic (not pixel/map) coordinates.
      @param g2 Rect top-right point, in geographic (not pixel/map) coordinates.
      @param g3 Rect bottom-right point, in geographic (not pixel/map) coordinates.
      @param g4 Rect bottom-left point, in geographic (not pixel/map) coordinates.
      @param select_mode How selection is to be performed: "reset" (default) will unselect all features before selecting new ones, 
                        "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
    */
    function boxSelect($g1, $g2, $g3, $g4, $select_mode) {

        $rect = ms_newRectObj();
        $rect->setExtent($g1->x, $g4->y, $g3->x, $g2->y);

        if ($this->select_item) {

            $succ = @$this->ms_layer->queryByRect($rect);
            if ($select_mode == 'reset') {
                $elements = array();
            } else {
                $elements = $this->selected;
            }
            if ($succ == MS_SUCCESS) {
                $n_res = $this->ms_layer->getNumResults();
                for ($i = 0; $i < $n_res; $i++) {
                    $res = $this->ms_layer->getResult($i);
                    $shp = $this->ms_layer->resultsGetShape($res->shapeindex, $res->tileindex);
                    $val = $shp->getValue($this->ms_layer, $this->select_item);
                    if ($select_mode == 'reset' || $select_mode == 'add') {
                        $elements[] = $val;
                    } else if ($select_mode == 'toggle') {
                        $key = array_search($val, $elements);
                        if ($key !== false) {
                            unset($elements[$key]);
                        } else {
                            $elements[] = $val;
                        }                        
                    }
                }
            }
            $this->setExpression($elements);

        } else if ($this->features) {

            $succ = @$this->ms_layer->queryByRect($rect);
            if ($succ == MS_SUCCESS) {
                $n_res = $this->ms_layer->getNumResults();
                for ($i = 0; $i < $n_res; $i++) {
                    $res = $this->ms_layer->getResult($i);
                    $shp = $this->ms_layer->resultsGetShape($res->shapeindex, $res->tileindex);
                    if ($select_mode == 'reset' || $select_mode == 'add') {
                        if (!in_array($res->shapeindex, $this->selected)) {
                            $this->selected[] = $res->shapeindex;                        
                            $shp->set('classindex', 1);
                        }
                    } else if ($select_mode == 'toggle') {
                        $key = array_search($res->shapeindex, $this->selected);
                        if ($key !== false) {
                            unset($this->selected[$key]);
                            $shp->set('classindex', 0);
                        } else {
                            $this->selected[] = $res->shapeindex;
                            $shp->set('classindex', 1);
                        }                        
                    }
                    $this->ms_layer->addFeature($shp);
                }
            }
        }

    }

    /*!
      If there are at least two classes, this will set an MS expression on the first one, using
      the supplied element IDs.

      @param elements List of item IDs to differentiate visually.
    */
    function setExpression($elements) {

        if (!$this->select_item) { return; }
        $ss = array();
        foreach ($elements as $el) {
            $ss[] = sprintf("'[%s]' ne '%s'", $this->select_item, $el);
        }
        $expr = implode(' and ', $ss);
        if ($expr) { $expr = sprintf('(%s)', $expr); };
        if ($this->ms_layer->numclasses >= 2) {
            $this->ms_layer->getClass(0)->setExpression($expr);
        }
        $this->selected = $elements;

    }

    /*!
      Sets a MS filter on the dlayer.

      @param elements List of item IDs.
      @param append (bool) Whether to add to the existing filter or not.
    */
    function setFilter($elements, $append = False) {

        if ($elements && $append) {
            $elements = array_merge($elements, $this->filtered);
        }
        if ($elements) {
            if ($this->is_shapefile) {
                $arr = array();
                foreach ($elements as $el) {
                    $arr[] = sprintf("'[%s]' eq '%s'", $this->select_item, $el);
                }
                $expr = implode(' or ', $arr);                
            } else {
                $expr = sprintf("%s in (%s)", $this->select_item, implode(',', $elements));
            }
            if ($expr) {
                $expr = sprintf('(%s)', $expr);
            }
        } else {
            $expr = "null";
        }
        $this->ms_layer->setFilter($expr);
        $this->filtered = $elements;

    }

    /*!
      Turns dlayer on/off.
      
      @param status On/off state of the dlayer (MS_ON | MS_OFF).
    */
    function setStatus($status) {
        assert(in_array($status, array(MS_ON, MS_OFF)));
        $this->ms_layer->set('status', $status);
    }

    /*!
      Returns the current status of the dlayer.

      @return MS_ON | MS_OFF.
    */
    function getStatus() {
        return $this->ms_layer->status;
    }

    /*!
      Removes all dlayer's selected items.
    */
    function clearSelected() {
        $this->selected = array();
        $this->setExpression(array());
    }

    /*!
      Removes all dlayer's features.
    */
    function clearFeatures() {
        $this->features = array();
    }

    /*!
      Saves the state of the dlayer in the session global PHP variable:
      filtered, selected, features items and the status are saved.
    */
    function saveStateInSession() {

        $hd = &$this->dmap->sess_mid['history'][count($this->dmap->sess_mid['history'])-1]['dlayers'];
        if (!isset($hd[$this->name])) {
            $hd[$this->name] = array();
        }
        $hd[$this->name]['filtered'] = $this->filtered;
        $hd[$this->name]['selected'] = $this->selected;
        $hd[$this->name]['features'] = $this->features;
        $hd[$this->name]['status'] = $this->getStatus();

    }

    /*!
      Sets the hover items, destined for the client. An hover item is defined by a dict triplet: {gx, gy, html} where
      gx/gy are geographic coordinates, and html is an information string, possibly HTML-formatted (as it will get injected
      in a div element.

      @param items List/assoc array of hover item triplets.
    */
    function setHoverItems($items) {
        $this->hover_items = array();
        foreach ($items as $item) {
            if ($item['html']) {
                $this->hover_items[] = array($item['gx'], $item['gy'], $item['html']);
            }
        }
        $this->hover_items_are_dirty = True;
    }

    /*!
      Adds a single hover item, and triggers the dirty and append modes.

      @param item Hover item dict triplet array(gx=>float, gy=>float, html=>str)
    */
    function addHoverItem($item) {
        if ($item['html']) {
            $this->hover_items[] = array($item['gx'], $item['gy'], $item['html']);
            $this->hover_items_are_dirty = True;
            $this->hover_items_in_append_mode = True;
        }
    }

    /*!
      @return The dlayer's hover items.
    */
    function getHoverItems() {
        return $this->hover_items;
    }

    /*!
      Once they are ready, add all the features (user-defined shapes).
    */
    function addFeatures() {
        ksort($this->features);
        foreach ($this->features as $fid => $f) {
            if (get($f, 'is_vis', True)) {
                $this->addFeature($f, $fid);
            }
        }
    }

    /*!
      Only defined in subclasses.
    */
    function addFeature($feature, $feature_id = Null) {
    }

    /*!
      Sets feature (user-defined shape) visibility.
    */
    function setFeatureVisibility($feature_id, $is_visible) {
        if ($array_key_exists($feature_id, $this->features)) {
            $this->features[$feature_id]['is_vis'] = $is_visible;
        }
    }

    /*!
      Only defined in subclasses.
    */
    function drawFeature($x, $y) {
    }

    /*!
      Select features (user-defined shape).

      @param features IDs of the selected features (can be a single item, i.e. not an array).
      @param select_mode How selection is to be performed: "reset" (default) will unselect all features before selecting new ones, 
                        "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
    */
    function selectFeatures($features, $select_mode) {

        if (!is_array($features)) {
            $features = array($features);
        }

        if ($select_mode == 'reset') { $this->selected = array(); }

        foreach ($features as $feature_id) {

            // is_null is needed here because in PHP it seems that: in_array(null, array(0)) is True!!
            $is_selected = (!is_null($feature_id) && in_array($feature_id, $this->selected));
            if ($select_mode == 'reset' || $select_mode == 'add') {
                if (!$is_selected) {
                    $this->selected[] = $feature_id;
                }                
            } else if ($select_mode == 'toggle') {
                if ($is_selected) {
                    unset($this->selected[array_search($feature_id, $this->selected)]);
                } else {
                    $this->selected[] = $feature_id;
                }
            }
        }
        $this->setExpression($this->selected);
    }

    /*!
      True if MS layer status is ON.
    */
    function isActive() {
        return ($this->getStatus() == MS_ON);
    }

}

/*!
  @ingroup core
  A point-specialized DLayer subclass.
*/
class PointDLayer extends DLayer {

    /*!
      PointDLayer constructor.
      
      @param name DLayer's name.
      @param dmap The DMap parent object.
    */
    function __construct($name, $dmap) {
        parent::__construct($name, $dmap);
    }

    /*!
      Add a point feature.

      @param feature: The geographic coordinates of the feature: array(gx=>float, gy=>float).
      @param feature_id If the feature has an id (not mandatory).
    */
    function addFeature($feature, $feature_id = Null) {

        $pt_shp = ms_newShapeObj(MS_SHAPE_POINT);
        $p = ms_newPointObj();
        $p->setXY($feature['gx'], $feature['gy']);                            
        $line = ms_newLineObj();
        $line->add($p);
        $pt_shp->add($line);
        $pt_shp->index = $this->shape_index;
        // is_null is needed here because in PHP it seems that: in_array(null, array(0)) is True!!
        if (!is_null($feature_id) && in_array($feature_id, $this->selected)) {
            $pt_shp->set('classindex', 1);
        }
        $this->ms_layer->addFeature($pt_shp);
        if (is_null($feature_id)) {
            $feature_id = $this->shape_index;
        }
        $this->features[$feature_id] = $feature;
        $this->shape_index = (int)$feature_id + 1;

    }

    /*!
      Calls addFeature with geographic x/y coords.

      @param x x coord.
      @param y y coord.       
    */
    function drawFeature($x, $y) {
        $p = pix2geo($this->dmap->ms_map, $x, $y);
        $this->addFeature(array('gx'=>$p->x, 'gy'=>$p->y));
    }

}

/*!
  @ingroup core
  A polygon-specialized DLayer subclass.
*/
class PolygonDLayer extends DLayer {

    /*!
      PolygonDLayer constructor.

      @param name DLayer's name.
      @param dmap The DMap parent object.
    */
    function __construct($name, $dmap) {
        parent::__construct($name, $dmap);
    }

    /*!
      Add a polygon feature.

      @param feature The geographic coordinates of the feature: array(coords=> array(array(x,y), array(x,y), ..)).
      @param feature_id If the feature has an id (not mandatory).
    */
    function addFeature($feature, $feature_id = Null) {

        $poly_shp = ms_newShapeObj(MS_SHAPE_POLYGON);
        $poly_line = ms_newLineObj();
        foreach ($feature['coords'] as $xy) {
            $p = ms_newPointObj();
            $p->setXY($xy[0], $xy[1]);
            $poly_line->add($p);
        }
        $poly_shp->add($poly_line);
        $poly_shp->index = $this->shape_index;
        // is_null is needed here because in PHP it seems that: in_array(null, array(0)) is True!!
        if (!is_null($feature_id) && in_array($feature_id, $this->selected)) {
            $poly_shp->set('classindex', 1);
        }
        $this->ms_layer->addFeature($poly_shp);
        if (is_null($feature_id)) {
            $feature_id = $this->shape_index;
        }
        $this->features[$feature_id] = $feature;
        $this->shape_index += 1;

    }


}

/*!
  @ingroup core
  A circle-specialized DLayer subclass.
*/
class CircleDLayer extends DLayer {

    /*!
      CircleDLayer constructor.

      @param name DLayer's name.
      @param dmap The DMap parent object.
    */
    function __construct($name, $dmap) {
        parent::__construct($name, $dmap);
    }

    /*!
      Add a circle feature.

      @param feature The geographic coordinates of the feature.
      @param feature_id If the feature has an id (not mandatory).
    */
    function addFeature($feature, $feature_id = Null) {

        $circle_shp = ms_newShapeObj(MS_SHAPE_LINE);
        $p1 = ms_newPointObj();
        $p2 = ms_newPointObj();
        $p1->setXY($feature['gx'] - $feature['rad'], $feature['gy'] + $feature['rad']);
        $p2->setXY($feature['gx'] + $feature['rad'], $feature['gy'] - $feature['rad']);
        $line = ms_newLineObj();
        $line->add($p1);
        $line->add($p2);
        $circle_shp->add($line);

        if (!is_null($feature_id)) {
            $circle_shp->set('index', $feature_id);
            //$circle_shp->index = $feature_id;
        } else {
            $circle_shp->set('index', $this->shape_index);
            //$circle_shp->index = $this->shape_index;
        }
        // is_null is needed here because in PHP it seems that: in_array(null, array(0)) is True!!
        if (!is_null($feature_id) && in_array($feature_id, $this->selected)) {
            $circle_shp->set('classindex', 1);
        }
        $this->ms_layer->addFeature($circle_shp);
        if (is_null($feature_id)) {
            $feature_id = $this->shape_index;
        }
        $this->features[$feature_id] = $feature;
        $this->shape_index = (int)$feature_id + 1;

    }

    /*!
        Calls addFeature with geographic x/y coords, default radius of 1000.

        @param x x coord.
        @param y y coord.
        @param rad Circle radius.
    */
    function drawFeature($x, $y, $rad = 1000) {
        $p = pix2geo($this->dmap->ms_map, $x, $y);
        $this->addFeature(array('gx'=>$p->x, 'gy'=>$p->y, 'rad'=>$rad, 'is_sel'=>False));
    }

}


/*!
  @ingroup core
  A line-specialized DLayer subclass.
*/
class LineDLayer extends DLayer {
    
    /*!
      LineDLayer constructor.

      @param name DLayer's name.
      @param dmap The DMap parent object.
    */
    function __construct($name, $dmap) {
        parent::__construct($name, $dmap);
    }

    /*!
      Add a line feature.

      @param feature The geographic coordinates of the feature=> array(gx0=>float, gy0=>float, gx1=>float, gy1=>float)
      @param feature_id If the feature has an id (not mandatory).
    */
    function addFeature($feature, $feature_id = Null) {

        $line_shp = ms_newShapeObj(MS_SHAPE_LINE);
        $line = ms_newLineObj();
        $p0 = ms_newPointObj();
        $p0->setXY($feature['gx0'], $feature['gy0']);
        $line->add($p0);
        $p1 = ms_newPointObj();
        $p1->setXY($feature['gx1'], $feature['gy1']);
        $line->add($p1);
        $line_shp->add($line);
        $line_shp->index = $this->shape_index;
        // is_null is needed here because in PHP it seems that: in_array(null, array(0)) is True!!
        if (!is_null($feature_id) && in_array($feature_id, $this->selected)) {
            $line_shp->set('classindex', 1);
        }
        $this->ms_layer->addFeature($line_shp);
        if (is_null($feature_id)) {
            $feature_id = $this->shape_index;
        }
        $this->features[$feature_id] = $feature;
        $this->shape_index += 1;

    }

    /*!
      Add a line feature, from coords in geo/pixel coords.
      
      @param from_pixel_coords (bool) If the input coords are from pixel, they will get converted to geo.
      @param x0, y0, x1, y1 Line coords.
    */
    function drawLine($x0, $y0, $x1, $y1, $from_pixel_coords = True) {

        if ($from_pixel_coords) {
            $p0 = pix2geo($this->dmap->ms_map, $x0, $y0);
            $p1 = pix2geo($this->dmap->ms_map, $x1, $y1);
        } else {
            $p0 = ms_newPointObj();
            $p0->setXY($x0, $y0);
            $p1 = ms_newPointObj();
            $p1->setXY($x1, $y1);
        }
        $this->addFeature(array('gx0'=>$p0->x, 'gy0'=>$p0->y, 'gx1'=>$p1->x, 'gy1'=>$p1->y, 'is_sel'=>False));

    }

}

/*!
  @ingroup core
  Dracones encapsulation of a MS map object. Please note that the 
  only differences with the Python version are: (1) since DMap cannot inherit from MapObj, 
  it has to hold a pointer to its object ($this->ms_map), and (2) it does not hold a 
  pointer to the global session variable.
*/
class DMap { 

    public $app;
    public $mid;
    public $app_name;
    public $ms_map; // this is a big difference with the Python version: since DMap cannot inherit from MapObj, 
    public $map_size_rel_to_vp; // it has to hold a pointer to its object
    public $dlayers;
    public $groups;
    public $sess;

    /*!
      DMap constructor.

      @param mid Main identifier: map widget ID
      @param use_viewport_geom (bool) Only False for the export function.
    */
    function __construct($mid, $use_viewport_geom = False) {

        global $dconf;
        $this->mid = $mid;
        $this->sess_mid = &$_SESSION[$mid];
        $this->app = $this->sess_mid['app'];
        $map_file = sprintf('%s/%s.map', $dconf[$this->app]['mapfile_path'], $this->sess_mid['map']);
        $this->ms_map = ms_newMapObj($map_file);
        if ($use_viewport_geom) {
            $this->map_size_rel_to_vp = 1;
        } else {
            $this->map_size_rel_to_vp = $this->sess_mid['msvp'];
        }
        $p = ms_newPointObj();
        $p->setXY($this->map_size_rel_to_vp * $this->sess_mid['mvpw'] / 2, $this->map_size_rel_to_vp * $this->sess_mid['mvph'] / 2);
        $this->ms_map->setSize($this->map_size_rel_to_vp * $this->sess_mid['mvpw'], $this->map_size_rel_to_vp * $this->sess_mid['mvph']);
        $this->ms_map->zoomPoint(-$this->map_size_rel_to_vp, $p, $this->ms_map->width, $this->ms_map->height, $this->ms_map->extent);
        $this->dlayers = array();
        $this->groups = array();
        foreach ($this->ms_map->getAllLayerNames() as $name) {
            $dlayer = createDLayerInstance($name, $this);
            $this->dlayers[$name] = $dlayer;
            if ($dlayer->group) {
                $this->groups[$dlayer->group][] = $name;
            }
        }
    }

    /*!
      Map panning in four directions.
      
      @param dir The panning direction: 'right' | 'left' | 'up' | 'down'.
    */
    function pan($dir) {

        $hnvp = ($this->map_size_rel_to_vp - 1) / 2;
        $x_disp = (($this->ms_map->extent->maxx - $this->ms_map->extent->minx) / $this->map_size_rel_to_vp) * ($hnvp - 0.5);
        $y_disp = (($this->ms_map->extent->maxy - $this->ms_map->extent->miny) / $this->map_size_rel_to_vp) * ($hnvp - 0.5);
        
        if ($dir == 'right') {
            $this->ms_map->setExtent($this->ms_map->extent->minx + $x_disp, $this->ms_map->extent->miny, $this->ms_map->extent->maxx + $x_disp, $this->ms_map->extent->maxy);
        } else if ($dir == 'left') {
            $this->ms_map->setExtent($this->ms_map->extent->minx - $x_disp, $this->ms_map->extent->miny, $this->ms_map->extent->maxx - $x_disp, $this->ms_map->extent->maxy);
        } else if ($dir == 'up') {
            $this->ms_map->setExtent($this->ms_map->extent->minx, $this->ms_map->extent->miny + $y_disp, $this->ms_map->extent->maxx, $this->ms_map->extent->maxy + $y_disp);
        } else if ($dir == 'down') {
            $this->ms_map->setExtent($this->ms_map->extent->minx, $this->ms_map->extent->miny - $y_disp, $this->ms_map->extent->maxx, $this->ms_map->extent->maxy - $y_disp);
        } else {
            assert(False);
        }

    }

    /*!
      Map +/-, point/box zoom.

      @param  x, y, w, h Pixel/map coords/dims
      @param mode: Zoom mode: 'in' | 'out'
      @param zs: Zoom size (int).
    */
    function zoom($x, $y, $w, $h, $mode, $zs) {

        if ($w && $h) {

            $hnvp = ($this->map_size_rel_to_vp - 1) / 2;
            $rect = ms_newRectObj();
            $rect->setExtent($x - ($hnvp * $w), $y - ($hnvp * $w), $x + $w + ($hnvp * $w), $y + $h + ($hnvp * $w));
            $this->ms_map->zoomRectangle($rect, $this->ms_map->width, $this->ms_map->height, $this->ms_map->extent);

        } else {

            if (!$zs) {
                $zoom_factor = 1;                
            } else {
                if ($mode == 'in') {
                    $zoom_factor = $zs;
                } else {
                    $zoom_factor = -$zs;
                }
            }
            $p = ms_newPointObj();
            $p->setXY((float)$x, (float)$y);
            $this->ms_map->zoomPoint($zoom_factor, $p, $this->ms_map->width, $this->ms_map->height, $this->ms_map->extent);
        }

    }

    /*!
      Sets the extent from rectObj dict.

      @param xt Extent as an assoc array=> array(minx=>float, maxx=>float, miny=>float, maxy=>float)
    */
    function setExtentFromDict($xt) {
        $this->ms_map->setExtent($xt['minx'], $xt['miny'], $xt['maxx'], $xt['maxy']);
    }

    /*!
      Performs a point or box selection on a set of dlayers, if their status is MS_ON.

      @param dlayers List of dlayers on which to perform the selection.
      @param x, y, w, h Selection coords in map/pixel coords.
      @param select_mode How selection is to be performed: "reset" (default) will unselect all features before selecting new ones, 
                        "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
    */
    function select($dlayers, $x, $y, $w = 0, $h = 0, $select_mode = 'reset') {

        if (is_string($dlayers)) {
            $dlayers = array($dlayers);
        }
        $selection_dlayers = array();
        foreach ($dlayers as $dlayer_name) {
            if (array_key_exists($dlayer_name, $this->groups)) {
                foreach ($this->groups[$dlayer_name] as $dlayer_name_in_grp) {
                    if ($this->hasDLayer($dlayer_name_in_grp) && $this->dlayers[$dlayer_name_in_grp]->isActive()) {
                        $selection_dlayers[] = $dlayer_name_in_grp;
                    }
                }
            } else if (array_key_exists($dlayer_name, $this->dlayers) && $this->dlayers[$dlayer_name]->isActive()) {
                $selection_dlayers[] = $dlayer_name;
            }
        }

        foreach ($selection_dlayers as $dlayer_to_select) {

            if ($w && $h) {
                $g1 = pix2geo($this->ms_map, $x, $y);
                $g2 = pix2geo($this->ms_map, $x + $w, $y);
                $g3 = pix2geo($this->ms_map, $x + $w, $y + $h);
                $g4 = pix2geo($this->ms_map, $x, $y + $h);
                $this->dlayers[$dlayer_to_select]->boxSelect($g1, $g2, $g3, $g4, $select_mode);
            } else {
                $p = pix2geo($this->ms_map, $x, $y);
                $this->dlayers[$dlayer_to_select]->pointSelect($p, $select_mode);
            }
        }

    }

    /*!
      Saves the map image and returns its URL.

      @return map image URL.
    */
    function getImageURL() {

        global $dconf;
        $img = $this->ms_map->draw();
        // app_mid_map_sessionid.imgtype
        $fn = sprintf("%s_%s_%s_%s.%s", $this->app, $this->mid, $this->sess_mid['map'], session_id(), $this->ms_map->imagetype);
        $img_url = sprintf("%s%s%s", $dconf['ms_tmp_url'], ($dconf['ms_tmp_url'][strlen($dconf['ms_tmp_url'])-1] == '/' ? '' : '/'), $fn);
        $img_path = sprintf("%s%s%s", $dconf['ms_tmp_path'], ($dconf['ms_tmp_path'][strlen($dconf['ms_tmp_path'])-1] == '/' ? '' : '/'), $fn);
        $img->saveImage($img_path);
        return $img_url;
    }

    /*!
      Returns a dlayer by name, throws an exception if not found.

      @param dlayer_name Name of the requested dlayer.
    */
    function getDLayer($dlayer_name) {
        assert($this->hasDLayer($dlayer_name));
        return $this->dlayers[$dlayer_name];
    }

    /*!
      @return Whether a dlayer is available or not.
    */
    function hasDLayer($dlayer_name) {
        return (array_key_exists($dlayer_name, $this->dlayers));
    }

    /*!
      Restores the state of all the dlayers found in the session variable.

      @param restore_extent If False, will stay with map default extent (bool).
    */
    function restoreStateFromSession($restore_extent = True) {

        $hist_idx = $this->sess_mid['history_idx'];
        foreach ($this->dlayers as $name => $dlayer) {
            $dlayer->restoreState($this->sess_mid['history'][$hist_idx]['dlayers'][$name]['filtered'],
                                  $this->sess_mid['history'][$hist_idx]['dlayers'][$name]['selected'],
                                  $this->sess_mid['history'][$hist_idx]['dlayers'][$name]['features'],
                                  $this->sess_mid['history'][$hist_idx]['dlayers'][$name]['status']);
        }
        $xt = $this->sess_mid['history'][$hist_idx]['extent'];
        if ($restore_extent && $xt) {
            $this->ms_map->setExtent($xt['minx'], $xt['miny'], $xt['maxx'], $xt['maxy']);
        }

    }

    /*!
      If required, shifts the history forward, and recursively calls the dlayers' saveStateInSession methods.

      @param shift_history_window (bool) To prevent an operation's resulting state to be stored in session, set to False.
    */
    function saveStateInSession($shift_history_window = True) {

        $hist_size = $this->sess_mid['history_size'];

        if ($shift_history_window) {

            /* 
               To preserve the forward order of the history items (i.e. an action at position i is "newer" than one at position < i),
               we need to detect the case where a new action is initiated somewhere in the history before then end (i.e. undo
               was used, once or more, and then a new action happened). This means that history_idx < history_size-1.
               The idea is that we will trim the "future part" of the history (i.e. the part to the right of history_idx) and 
               start from there.
               Example: a b c d e
               If we return back to element c, and issue new action f
               the outcome should be: _ a b c f
               Note that we must use a special "init" padding for the first element (_), to prevent going back to it.
               The same mechanism is also used in the client module (for hover items history) 
            */
            $hist_idx = $this->sess_mid['history_idx'];
            if ($hist_idx != ($hist_size - 1)) {
                $prev_hist_cell = array_deep_copy($this->sess_mid['history'][$hist_idx]);
                // shift subset of history (0 to history_idx) to the far right (minus 1)
                $hist_copy = array_deep_copy($this->sess_mid['history']);
                for ($i = 0; $i <= $hist_idx; $i++) {
                    $h = $hist_size - $hist_idx - 2 + $i;
                    $this->sess_mid['history'][$h] = $hist_copy[$i];
                    if ($i == 0 && $h > 0) { // special case: prevent going back to previous part of history (using an 'init' item)
                        $this->sess_mid['history'][$h-1]['init'] = True;
                    }
                }
                // add new cell at last slot
                $this->sess_mid['history'][$hist_size-1] = newHistoryCell(); // add new cell

            } else {

                // new action is initiated at the end of history: simply append a new cell at the 
                // right, and pop the oldest one at the left
                $prev_hist_cell = array_deep_copy($this->sess_mid['history'][$hist_size-1]);
                $this->sess_mid['history'][] = newHistoryCell(); // add new cell
                array_shift($this->sess_mid['history']); // remove oldest one

            }

            // copy every prev cell element
            foreach ($prev_hist_cell as $item => $value) {
                if ($item != 'dlayers' && $item != 'extent') {
                    $this->sess_mid['history'][$hist_size - 1][$item] = $prev_hist_cell[$item];
                }
            }
        }

        $this->sess_mid['history_idx'] = ($this->sess_mid['history_size'] - 1);
        $this->sess_mid['history'][$hist_size - 1]['extent'] = $this->getExtent();
        foreach ($this->dlayers as $name => $dlayer) {
            $dlayer->saveStateInSession();
        }
    }

    /*!
      Hover items for the whole map, as a dict with keys as dlayer names, and values as dicts with 'append' (bool)
      and 'items' (list of hover item triplets). If in 'append' mode, the hover items for a given dlayer will not
      replace the previous ones.
      
      @return Hover items for the whole map (dict: {dlayer: {append: bool, items: [(hover item triplets)]}}).
    */
    function getHoverItems() {
        $map_hover_items = array();
        foreach ($this->dlayers as $name => $dlayer) {
            if ($dlayer->hover_items_are_dirty) {
                $map_hover_items[$name] = array('append' => $dlayer->hover_items_in_append_mode, 'items' => $dlayer->hover_items);
            }
        }
        return $map_hover_items;
    }

    /*!
      Selection dict for the whole map.
      
      @return {dlayer: [..sel IDs], ..}.
    */
    function getSelection() {
        $selection_map = array();
        foreach ($this->dlayers as $name => $dlayer) {
          // if ($dlayer->selected) {
            $selection_map[$name] = $dlayer->selected;
          // }
        }
        return $selection_map;
    }

    /*!
      @return The extent as an assoc array.
    */
    function getExtent() {
        return rectObjToDict($this->ms_map->extent);
    }

    /*!
      Clears a dlayer with respecto to certain item types: selected,
      features, filtered, all.
      
      @param dlayer_name Name of the cleared dlayer.
      @param what Target attribute for clear: 'selected', 'features', 'filtered', 'all'.
    */
    function clearDLayer($dlayer_name, $what = 'all') {

        if (array_key_exists($dlayer_name, $this->groups)) {

            foreach ($this->groups[$dlayer_name] as $dlayer_name_grp) {

                if (!$this->hasDLayer($dlayer_name_grp) || $this->dlayers[$dlayer_name_grp]->getStatus() != MS_ON) {
                    continue;
                }
                if (in_array($what, array('selected', 'all'))) {
                    $this->dlayers[$dlayer_name_grp]->clearSelected();
                }
                if (in_array($what, array('features', 'all'))) {
                    $this->dlayers[$dlayer_name_grp]->clearFeatures();
                    $this->dlayers[$dlayer_name_grp]->hover_items_are_dirty = True;
                }
                if (in_array($what, array('filtered', 'all'))) {
                    $this->dlayers[$dlayer_name_grp]->setFilter(array());
                    $this->dlayers[$dlayer_name_grp]->hover_items_are_dirty = True;
                }
            }

        } else {

            if (!$this->hasDLayer($dlayer_name) || $this->dlayers[$dlayer_name]->getStatus() != MS_ON) {
                return;
            }
            if (in_array($what, array('selected', 'all'))) {
                $this->dlayers[$dlayer_name]->clearSelected();
            }
            if (in_array($what, array('features', 'all'))) {
                $this->dlayers[$dlayer_name]->clearFeatures();
                $this->dlayers[$dlayer_name]->hover_items_are_dirty = True;
            }
            if (in_array($what, array('filtered', 'all'))) {
                $this->dlayers[$dlayer_name]->setFilter(array());
                $this->dlayers[$dlayer_name]->hover_items_are_dirty = True;
            }
        }

    }

    /*!
      Recursively calls addFeatures for all existing dlayers.
    */
    function addDLayerFeatures() {
        foreach ($this->dlayers as $name => $dlayer) {
            $dlayer->addFeatures();
        }
    }

    /*!
      @param dlayer_name Name of the dlayer (if group, only the active/displayed ones) for which we want the selected elements.
      @return List of selected element (IDs) for a given dlayer.
    */
    function getSelected($dlayer_name) {

        if (array_key_exists($dlayer_name, $this->groups)) {
            $selected = array();
            foreach ($this->groups[$dlayer_name] as $dlayer_name_in_grp) {
                if ($this->hasDLayer($dlayer_name_in_grp) && $this->dlayers[$dlayer_name_in_grp]->isActive()) {
                    $selected = array_merge($selected, $this->dlayers[$dlayer_name_in_grp]->selected);
                }
            }
            return $selected;
        } else {
            if ($this->hasDLayer($dlayer_name)) {
                return $this->dlayers[$dlayer_name]->selected;
            } else {
                return array();
            }            
        }

    }

    /*!
      Wrapper for dlayer.selectFeatures, useful if dlayer is a group.

      @param dlayer_name Name of dlayer or group of dlayers.
      @param features IDs of the selected features (can be a single item).
      @param select_mode How selection is to be performed on a DLayer: "reset" (default) will unselect all features before selecting new ones, 
                        "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
    */
    function selectFeatures($dlayer_name, $features, $select_mode) {

        if (array_key_exists($dlayer_name, $this->groups)) {
            foreach ($this->groups[$dlayer_name] as $dlayer_name_in_grp) {
                if ($this->hasDLayer($dlayer_name_in_grp) && $this->dlayers[$dlayer_name_in_grp]->isActive()) {
                    $this->dlayers[$dlayer_name_in_grp]->selectFeatures($features, $select_mode);
                }
            }
        } else {
            if ($this->hasDLayer($dlayer_name) && $this->dlayers[$dlayer_name]->isActive()) {
                $this->dlayers[$dlayer_name]->selectFeatures($features, $select_mode);
            }
        }

    }

    /*!
      @param group_name Name of dlayer group.
      @return Active/displayed DLayers that are member of a given group.
    */
    function getActiveDLayersForGroup($group_name) {
        $active_dlayers = array();
        foreach (get($this->groups, $group_name, array()) as $dlayer_name_in_grp) {
          if ($this->hasDLayer($dlayer_name_in_grp) && $this->dlayers[$dlayer_name_in_grp]->isActive()) {
            $active_dlayers[] = $dlayer_name_in_grp;
          }
        }
        return $active_dlayers;
    }

    /*!
      Sets a user-defined history item in the current session's history cell.
      The item gets copied every time the history is shifter, so it can be 
      recalled later, using getHistoryItem. IMPORTANT: This must be called 
      *before* the endDracones call.

      @param item Name of the item to set.
      @param value Value of the item to set (restricted to built-in types).
    */
    function setHistoryItem($item, $value) {
        $hist_idx = $this->sess_mid['history_idx'];
        $this->sess_mid['history'][$hist_idx][$item] = $value;
    }

    /*!
      Retrieves a user-defined history item.

      @param item Name of the item to retrieve.
      @return The value of the requested history item.
    */
    function getHistoryItem($item) {
        $hist_idx = $this->sess_mid['history_idx'] - 1;
        assert(array_key_exists($item, $this->sess_mid['history'][$hist_idx]));
        return $this->sess_mid['history'][$hist_idx][$item];
    }

}

?>
