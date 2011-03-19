#  Draoones Web-Mapping Framework
#  ==============================
#
#  http://surveillance.mcgill.ca/dracones
#  Copyright (c) 2009, Christian Jauvin
#  All rights reserved. See LICENSE.txt for BSD license notice

"""
Main Dracones components and logic.
"""

import sys, re, os, copy, time, datetime, os.path, copy
from dracones.conf import *


def pix2geo(m, px, py):
    """
    Pixel to geographical coordinates conversion.

    @type m: mapscript.mapObj (can be a DMap object)
    @param m: the map object from which the extent will be extracted.
    @type px: float
    @param px: x coord in pixel value.
    @type py: float
    @param py: y coord in pixel value.
    @return: A mapscript.pointObj, with x and y properties.
    """
    dx = m.extent.maxx - m.extent.minx
    dy = m.extent.maxy - m.extent.miny
    dxpp = dx / m.width
    dypp = dy / m.height
    geox = m.extent.minx + (dxpp * px)
    geoy = m.extent.maxy - (dypp * py)
    p = pointObj(geox, geoy)
    return p


def geo2pix(m, gx, gy):
    """
    Geographical to pixel coordinates conversion.

    @type m: mapscript.mapObj (can be a DMap object)
    @param m: the map object from which the extent will be extracted.
    @type gx: float
    @param gx: x coord in geo value.
    @type gy: float
    @param gy: y coord in geo value.
    @return: A (px, py) float tuple.
    """
    def _geo2pix(geo_pos, pix_min, pix_max, geo_min, geo_max, inv):
        w_geo = abs(geo_max - geo_min)
        w_pix = abs(pix_max - pix_min)
        if w_geo <= 0: return 0
        g2p = w_pix / w_geo
        if inv: del_geo = geo_max - geo_pos
        else: del_geo = geo_pos - geo_min
        del_pix = del_geo * g2p
        pos_pix = pix_min + del_pix
        return int(pos_pix)
    px = _geo2pix(gx, 0, m.width, m.extent.minx, m.extent.maxx, False)
    py = _geo2pix(gy, 0, m.height, m.extent.miny, m.extent.maxy, True)
    return (px, py)


def rectObjToDict(r):
    """
    mapscript.rectObj to Python dict. Is used in particular for map extent.

    @type r: mapscript.rectObj
    @param r: A mapscript.rectObj object.
    @return: {minx:.., miny:.., maxx:.., maxy:..}.
    """    
    return { 'minx' : r.minx, 'miny' : r.miny, 'maxx' : r.maxx, 'maxy' : r.maxy }
    

def newHistoryCell():
    """
    Creates an HistoryCell to store in the session variable.

    @return: {dlayers:.., extent:..}
    """
    return { 'dlayers' : {}, 'extent' : None }


def createDLayerInstance(name, dmap):
    """
    Instantiation of the proper subclass of DLayer, based on the layer type (a mapping from
    MS layer type to DLayer type).

    @type name: str
    @param name: Name of the layer.
    @type dmap: DMap
    @param dmap: The DMap containing the layer.
    @return: An instance of a subclassed DLayer, according to the MS type of the layer.
    """
    assert dmap.getLayerByName(name), "Layer '%s' does not exist" % name
    layer_type = dmap.getLayerByName(name).type
    if layer_type == MS_LAYER_POINT:
        return PointDLayer(name, dmap)
    elif layer_type == MS_LAYER_POLYGON:
        return PolygonDLayer(name, dmap)
    elif layer_type == MS_LAYER_CIRCLE:
        return CircleDLayer(name, dmap)
    elif layer_type == MS_LAYER_LINE:
        return LineDLayer(name, dmap)
    else:
        return DLayer(name, dmap)


class DLayer(object):
    """
    Dracones encapsulation of a MS layer object.
    """

    def __init__(self, name, dmap):
        """
        DLayer constructor.

        @type name: str
        @param name: Name of the layer (must correspond to an existing MS layer).
        @type dmap: DMap
        @param dmap: The DMap object containing the layer.        
        """
        self.name = name
        self.dmap = dmap
        self.ms_layer = dmap.getLayerByName(name) #: Pointer to the underlying MS mapscript.layerObj (via the DMap's central tile, see DMap doc).
        self.selected = [] #: List of currently selected items/features.
        self.is_filtered = (self.ms_layer.filteritem is not None) #: Whether the underlying MS layer contains a filteritem directive or not.
        self.filtered = [] #: List of currently filtered items/features.
        self.features = {} #: dict: id -> {feature attributes..}.
        self.hover_items = [] #: List of (gx, gy, html) triplets.
        self.hover_items_are_dirty = False
        self.hover_items_in_append_mode = False
        self.group = self.ms_layer.group 
        self.shape_index = 0
        self.is_shapefile = False #: Shapefile or PostGIS source.
        if self.ms_layer.data:
            # search from SQL pattern '* from *...'
            self.is_shapefile = not re.match('.* *from *.*', self.ms_layer.data, re.IGNORECASE)
        self.select_item = None #: Corresponds to a MS filter or class item (must be set for the layer to be queryable).
        if self.is_filtered:
            self.select_item = self.ms_layer.filteritem
        else:
            self.select_item = self.ms_layer.classitem

        # PostGIS connection string override mechanism
        if self.ms_layer.connectiontype == MS_POSTGIS and not self.ms_layer.connection:
            if dconf[dmap.app_name].get('map', {}).get('postgis_connection', None):
                self.ms_layer.connection = dconf[dmap.app_name]['map']['postgis_connection']

                        
    def queryByAttributes(self, attr, value, hover_item_html_template = ""):
        """
        This performs mapscript.queryByAttributes on the underlying MS
        layer (resulting in a setFilter operation) and it also builds
        the set of corresponding hover items, using the desired fields
        in the supplied HTML template. Note that a 'select_item' must
        be defined within this DLayer (this corresponds to a CLASSITEM
        or FILTERITEM clause in the MS layer).

        @type attr: str
        @param attr: The name of the queried attribute.
        @type value: str (or whatever else that will coerced into a string)
        @param value: Value of the queried attribute.
        @type hover_item_html_template: str
        @param hover_item_html_template: An HTML-based field name matching template for the hovering mechanism, used by the client.
                                            The string "<b>{name} {age}</b>" could result for instance in "<b>Bob 51</b>".
        """
        if not self.select_item: assert False, 'select_item (classitem or filteritem) must be set for a queryByAttributes'
        if isinstance(value, list):
            value = [str(v) for v in value]
        else:
            value = str(value)
        if self.is_shapefile:
            if not value:
                value_expr = "/null/"
            elif isinstance(value, list):
                value_expr = "/%s/" % ("|".join(["^%s$" % v for v in value]))
            else:
                value_expr = "/^%s$/" % value
        else:
            if not value:
                value_expr = "%s in (null)" % attr            
            elif isinstance(value, list):
                value_expr = "%s in (%s)" % (attr, ",".join(["'%s'" % s for s in value]))
            else:
                value_expr = "%s = '%s'" % (attr, value)
        filtered = []
        hover_items = []
        hover_item_html_tmpl_fields = []
        if hover_item_html_template:
            hover_item_html_tmpl_fields = re.findall('{(\w+)}', hover_item_html_template)
        hover_item_html_tmpl_fields = [f.lower() for f in hover_item_html_tmpl_fields]
        succ = self.ms_layer.queryByAttributes(self.dmap, attr, value_expr, MS_MULTIPLE)
        if succ == MS_SUCCESS:
            self.ms_layer.open()
            n_res = self.ms_layer.getNumResults()
            for i in range(n_res):
                res = self.ms_layer.getResult(i)
                if msGetVersionInt() >= 50600:
                    shp = shapeObj(MS_SHAPE_NULL)
                    self.ms_layer.resultsGetShape(shp, res.shapeindex, res.tileindex)
                else:
                    shp = self.ms_layer.getFeature(res.shapeindex)
                wkt = shp.toWKT()

                hover_item = { 'gx':None, 'gy':None, 'html':None}
                hover_item_map = {}

                m = re.match('POINT *[(](.*) (.*)[)]', wkt)
                if m:
                    hover_item['gx'] = m.group(1)
                    hover_item['gy'] = m.group(2)

                # there's no item map so no other choice than searching for the required fields

                key_val = None

                for i in range(shp.numvalues):

                    # collect key_val
                    if self.ms_layer.getItem(i).lower() == self.select_item.lower():
                        key_val = shp.getValue(i)

                    # collect hover values for corresponding fields
                    if self.ms_layer.getItem(i).lower() in hover_item_html_tmpl_fields:
                        hover_item_map[self.ms_layer.getItem(i).lower()] = shp.getValue(i)
                        
                if key_val:

                    hover_item_html = hover_item_html_template
                    for f in hover_item_html_tmpl_fields:
                        hover_item_html = hover_item_html.replace('{%s}' % f, hover_item_map.get(f, "?"))
                    hover_item['html'] = hover_item_html

                    filtered.append(key_val)
                    hover_items.append(hover_item)
                        
            self.ms_layer.close()
        if self.is_filtered:
            self.setFilter(filtered)
        self.setHoverItems(hover_items)


    def getRecordAttributes(self, attr, value):
        """
        Retrieves all the attributes for a record identified by a pair attribute/value.

        @type attr: str
        @param attr: Name of the key attribute.
        @type value: str
        @param value: Value of the key attribute.
        @return: An attribute:value dict.
        """
        if not self.select_item: assert False, 'select_item (classitem or filteritem) must be set for a queryByAttributes'
        if self.is_shapefile:
            value_expr = "/^%s$/" % value
        else: 
            value_expr = "%s = '%s'" % (attr, value)
        attributes = {}
        succ = self.ms_layer.queryByAttributes(self.dmap, attr, value_expr, MS_SINGLE)
        if succ == MS_SUCCESS:
            self.ms_layer.open()
            res = self.ms_layer.getResult(0)
            if msGetVersionInt() >= 50600:
                shp = shapeObj(MS_SHAPE_NULL)
                self.ms_layer.resultsGetShape(shp, res.shapeindex, res.tileindex)
            else:
                shp = self.ms_layer.getFeature(res.shapeindex)
            for i in range(shp.numvalues):
                attributes[self.ms_layer.getItem(i)] = shp.getValue(i)
            self.ms_layer.close()
        return attributes


    def restoreState(self, already_filtered, already_selected, existing_features, status):
        """
        Restore the state of the DLayer: filter, select, features, status.

        @type already_filtered: list
        @param already_filtered: List of filtered item IDs.
        @type already_selected: list
        @param already_selected: List of selected item IDs.
        @type existing_features: dict: id -> {feature attributes..}
        @param existing_features: Dict of feature attributes (identified by id).
        @type status: mapscript.MS_ON | mapscript.MS_OFF
        @param status: On/off status of the DLayer.
        """
        if self.is_filtered:
            self.setFilter(already_filtered)
        self.setExpression(already_selected)
        self.selected = already_selected
        self.filtered = already_filtered
        self.features = existing_features
        self.setStatus(status)
        

    def pointSelect(self, p, select_mode):
        """
        Will select item at point, using
        mapscript.layerObj.queryByPoint. If the dlayer has a
        select_item defined (CLASSITEM or FILTERITEM), it will build
        an MS expression, to be applied on the first class of the
        layer (if there are at least two; if not, the selection has no
        visual effect).  If not, it will modify directly the
        classindex of the selected feature (if any).

        @type p: mapscript.pointObj
        @param p: Selection point, in geographic (not pixel/map) coordinates.
        @type select_mode: str 
        @param select_mode: How selection is to be performed: "reset" (default) will unselect all features before selecting new ones, 
                            "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
        """
        if self.select_item:

            succ = self.ms_layer.queryByPoint(self.dmap, p, MS_SINGLE, -1)
            if select_mode == 'reset':
                elements = []
            else:
                elements = self.selected[:]
            if succ == MS_SUCCESS:
                res = self.ms_layer.getResult(0)
                self.ms_layer.open() # useless with new query mechanism
                if msGetVersionInt() >= 50600:
                    shp = shapeObj(MS_SHAPE_NULL)
                    self.ms_layer.resultsGetShape(shp, res.shapeindex, res.tileindex)
                else:
                    shp = self.ms_layer.getFeature(res.shapeindex)   
                for i in range(shp.numvalues):
                    if self.ms_layer.getItem(i).lower() == self.select_item.lower():
                        val = shp.getValue(i)
                        if select_mode in ['reset', 'add']:
                            elements.append(val)
                        elif select_mode == 'toggle':
                            if val in elements:
                                elements.remove(val)
                            else:
                                elements.append(val)
                        break
                self.ms_layer.close() # useless with new query mechanism
            self.setExpression(elements)

        elif self.features:

            succ = self.ms_layer.queryByPoint(self.dmap, p, MS_SINGLE, -1)
            if succ == MS_SUCCESS:
                res = self.ms_layer.getResult(0)
                self.ms_layer.open() # useless with new query mechanism
                if msGetVersionInt() >= 50600:
                    shp = shapeObj(MS_SHAPE_NULL)
                    self.ms_layer.resultsGetShape(shp, res.shapeindex, res.tileindex)
                else:
                    shp = self.ms_layer.getFeature(res.shapeindex)
                ssi = str(res.shapeindex) # string shapeindex
                if select_mode in ['reset', 'add']:
                    self.selected.append(ssi)
                elif select_mode == 'toggle':
                    if ssi in self.selected:
                        self.selected.remove(ssi)
                        shp.classindex = 0
                    else:
                        self.selected.append(ssi)                        
                        shp.classindex = 1
                self.ms_layer.addFeature(shp)
                self.ms_layer.close() # useless with new query mechanism
            

    def boxSelect(self, g1, g2, g3, g4, select_mode):
        """
        Will select item in a rectangle, using
        mapscript.layerObj.queryByRect. If the dlayer has a
        select_item defined (CLASSITEM or FILTERITEM), it will build
        an MS expression, to be applied on the first class of the
        layer (if there are at least two; if not, the selection has no
        visual effect).  If not, it will modify directly the
        classindex of the selected features (if any).

        @type g1: mapscript.pointObj
        @param g1: Rect top-left point, in geographic (not pixel/map) coordinates.
        @type g2: mapscript.pointObj
        @param g2: Rect top-right point, in geographic (not pixel/map) coordinates.
        @type g3: mapscript.pointObj
        @param g3: Rect bottom-right point, in geographic (not pixel/map) coordinates.
        @type g4: mapscript.pointObj
        @param g4: Rect bottom-left point, in geographic (not pixel/map) coordinates.
        @type select_mode: str 
        @param select_mode: How selection is to be performed: "reset" (default) will unselect all features before selecting new ones, 
                            "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
        """
        # warning here: this rect is in geo coords, and miny/maxy are inverted
        rect = rectObj(g1.x, g4.y, g3.x, g2.y)

        if self.select_item:

            succ = self.ms_layer.queryByRect(self.dmap, rect)
            if select_mode == 'reset':
                elements = []
            else:
                elements = self.selected[:]
            if succ == MS_SUCCESS:
               self.ms_layer.open() # useless with new query mechanism
               n_res = self.ms_layer.getNumResults()
               for i in range(n_res):
                   res = self.ms_layer.getResult(i)
                   if msGetVersionInt() >= 50600:
                       shp = shapeObj(MS_SHAPE_NULL)
                       self.ms_layer.resultsGetShape(shp, res.shapeindex, res.tileindex)
                   else:
                       shp = self.ms_layer.getFeature(res.shapeindex)                     
                   for j in range(shp.numvalues):
                       if self.ms_layer.getItem(j).lower() == self.select_item.lower():
                           val = shp.getValue(j)
                           if select_mode in ['reset', 'add']:
                               elements.append(val)
                           elif select_mode == 'toggle':
                               if val in elements:
                                   elements.remove(val)
                               else:
                                   elements.append(val)
                           break
               self.ms_layer.close() # useless with new query mechanism
            self.setExpression(elements)

        elif self.features:

            succ = self.ms_layer.queryByRect(self.dmap, rect)
            if succ == MS_SUCCESS:
                self.ms_layer.open() # useless with new query mechanism
                n_res = self.ms_layer.getNumResults()
                for j in range(n_res):
                    res = self.ms_layer.getResult(j)
                    if msGetVersionInt() >= 50600:
                        shp = shapeObj(MS_SHAPE_NULL)
                        self.ms_layer.resultsGetShape(shp, res.shapeindex, res.tileindex)
                    else:
                        shp = self.ms_layer.getFeature(res.shapeindex)                     
                    ssi = str(res.shapeindex) # string shapeindex
                    if select_mode in ['reset', 'add']:
                        self.selected.append(ssi)
                        shp.classindex = 1
                    elif select_mode == 'toggle':
                        if ssi in self.selected:
                            self.selected.remove(ssi)
                            shp.classindex = 0
                        else:
                            self.selected.append(ssi)                        
                            shp.classindex = 1
                    self.ms_layer.addFeature(shp)
                self.ms_layer.close() # useless with new query mechanism
            

    # goes with self.selected
    def setExpression(self, elements):
        """
        If there are at least two classes, this will set an MS expression on the first one, using
        the supplied element IDs.

        @type elements: list
        @param elements: List of item IDs to differentiate visually.
        """
        if not self.select_item: return
        expr = " and ".join(["'[%s]' ne '%s'" % (self.select_item, s) for s in elements])
        if expr: expr = "(%s)" % expr
        if self.ms_layer.numclasses >= 2:
            self.ms_layer.getClass(0).setExpression(expr)
#            self.dmap.getLayerByName(self.name).getClass(0).setExpression(expr)
        self.selected = elements

        
    # goes with self.filtered
    def setFilter(self, elements, append = False):
        """
        Sets a MS filter on the dlayer.

        @type elements: list
        @param elements: List of item IDs.
        @type append: bool
        @param append: Whether to add to the existing filter or not.
        """        
        if elements and append:
            elements.extend(self.filtered)
        if elements:
            elements = [str(x) for x in elements]
            if self.is_shapefile:
                expr = " or ".join(["'[%s]' eq '%s'" % (self.select_item, s) for s in elements])
            else:
                expr = "%s in (%s)" % (self.select_item, ",".join(elements))
            if expr:
                expr = "(%s)" % expr
        else:
            expr = "null"
        self.ms_layer.setFilter(expr)
#        self.dmap.getLayerByName(self.name).setFilter(expr)
        self.filtered = elements
        

    def setStatus(self, status):
        """
        Turns dlayer on/off.

        @type status: mapscript.MS_ON | mapscript.MS_OFF
        @param status: On/off state of the dlayer.
        """
        assert status in [MS_ON, MS_OFF]
        self.ms_layer.status = status

    def getStatus(self):
        """
        Returns the current status of the dlayer.

        @return: mapscript.MS_ON | mapscript.MS_OFF.
        """
        return self.ms_layer.status

    def clearSelected(self):
        """
        Removes all dlayer's selected items.
        """
        del self.selected[:]
        self.setExpression([])


    def clearFeatures(self):
        """
        Removes all dlayer's features.
        """
        self.features = {}


    # "inSession" emphasizes the fact that the session var is modified 
    def saveStateInSession(self):
        """
        Saves the state of the dlayer in the member session variable:
        filtered, selected, features items and the status are saved.
        """
        self.dmap.sess_mid['history'][-1]['dlayers'].setdefault(self.name, {})['filtered'] = self.filtered
        self.dmap.sess_mid['history'][-1]['dlayers'].setdefault(self.name, {})['selected'] = self.selected
        self.dmap.sess_mid['history'][-1]['dlayers'].setdefault(self.name, {})['features'] = self.features
        self.dmap.sess_mid['history'][-1]['dlayers'].setdefault(self.name, {})['status'] = self.getStatus()

    # accepts both items = { id -> {gx,gy,html}, ... }
    #          and items = [{gx,gy,html}, ...]
    # html must be set to something, if not, the item is not added
    def setHoverItems(self, items):
        """
        Sets the hover items, destined for the client. An hover item is defined by a dict triplet: {gx, gy, html} where
        gx/gy are geographic coordinates, and html is an information string, possibly HTML-formatted (as it will get injected
        in a div element.

        @type items: either a dict: {id: {gx:float, gy:float, html:str}} or list of {gx:float, gy:float, html:str}
        @param items: List/dict of hover item triplets.
        """
        del self.hover_items[:]
        if isinstance(items, dict):
            for id, item in items.items():
                if item['html']:
                    self.hover_items.append((item['gx'], item['gy'], item['html']))
        else:
            for item in items:
                if item['html']:
                    self.hover_items.append((item['gx'], item['gy'], item['html']))
        self.hover_items_are_dirty = True

    def addHoverItem(self, item):
        """
        Adds a single hover item, and triggers the dirty and append modes.

        @type item: dict triplet: {gx:float, gy:float, html:str}
        @param item: Hover item dict triplet.
        """
        if item['html']:
            self.hover_items.append((item['gx'], item['gy'], item['html']))
            self.hover_items_are_dirty = True
            self.hover_items_in_append_mode = True
        

    def getHoverItems(self):
        """
        @return: The dlayer's hover items.
        """
        return self.hover_items


    # very important that the feature_id's are sorted here, because
    # the shape_indexes must start at zero
    def addFeatures(self):
        """
        Once they are ready, add all the features (user-defined shapes).
        """
        for fid, f in sorted(self.features.items()):
            if f.get('is_vis', True):
                self.addFeature(f, fid)
                

    # defined in subclasses: point, polygon, circle
    def addFeature(self, feature, feature_id = None):
        """
        Only defined in subclasses.
        """
        pass
            

    def setFeatureVisibility(self, feature_id, is_visible):
        """
        Sets feature (user-defined shape) visibility.
        """
        feature_id = str(feature_id)
        if feature_id in self.features:
            self.features[feature_id]['is_vis'] = is_visible

    # defined in subclasses: point, circle
    def drawFeature(self, x, y):
        """
        Only defined in subclasses.
        """
        pass

    def selectFeatures(self, features, select_mode):
        """
        Select features (user-defined shape).

        @type features: list or single item
        @param features: IDs of the selected features.
        @type select_mode: str 
        @param select_mode: How selection is to be performed: "reset" (default) will unselect all features before selecting new ones, 
                            "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
        """
        if not getattr(features, '__iter__', False):
            features = [features]
        features = [str(s) for s in features]
        if select_mode == 'reset': del self.selected[:]
        for feature_id in features:
            if select_mode in ['reset', 'add']:
                if feature_id not in self.selected:
                    self.selected.append(feature_id)
            elif select_mode == 'toggle':
                if feature_id in self.selected: self.selected.remove(feature_id)
                else: self.selected.append(feature_id)
        self.setExpression(self.selected)


    def isActive(self):
        """
        True if MS layer status is ON.
        """
        return (self.getStatus() == MS_ON)

                
class PointDLayer(DLayer):
    """
    A point-specialized DLayer subclass.
    """

    def __init__(self, name, dmap):
        """
        PointDLayer constructor.

        @type name: str
        @param name: DLayer's name.
        @type dmap: dracones.DMap
        @param dmap: The DMap parent object.
        """
        super(PointDLayer, self).__init__(name, dmap)


    def addFeature(self, feature, feature_id = None):
        """
        Add a point feature.

        @type feature: dict {gx:float, gy:float}
        @param feature: The geographic coordinates of the feature.
        @type feature_id: str | int
        @param feature_id: If the feature has an id.
        """
        if feature_id: feature_id = str(feature_id)
        # todo: assert feature structure
        pt_shp = shapeObj(MS_SHAPE_POINT)
        p = pointObj(feature['gx'], feature['gy'])
        line = lineObj()
        line.add(p)
        pt_shp.add(line)
        pt_shp.index = self.shape_index
        if feature_id in self.selected:
            pt_shp.classindex = 1
        self.ms_layer.addFeature(pt_shp)
        if not feature_id:
            feature_id = str(self.shape_index)
        self.features[feature_id] = feature
        self.shape_index += 1


    def drawFeature(self, x, y):
        """
        Calls addFeature with geographic x/y coords.

        @type x: float
        @param x: x coord
        @type y: float
        @param y: y coord        
        """
        p = pix2geo(self.dmap, x, y)
        self.addFeature({'gx':p.x, 'gy':p.y})


class PolygonDLayer(DLayer):
    """
    A polygon-specialized DLayer subclass.
    """

    def __init__(self, name, dmap):
        """
        PolygonDLayer constructor.

        @type name: str
        @param name: DLayer's name.
        @type dmap: dracones.DMap
        @param dmap: The DMap parent object.
        """
        super(PolygonDLayer, self).__init__(name, dmap)

    # feature: {'coords': [(x,y),(x,y),..]}
    def addFeature(self, feature, feature_id = None):
        """
        Add a polygon feature.

        @type feature: dict: {coords: [(x,y), (x,y), ..]}
        @param feature: The geographic coordinates of the feature.
        @type feature_id: str | int
        @param feature_id: If the feature has an id.
        """
        if feature_id: feature_id = str(feature_id)
        # todo: assert feature structure
        poly_shp = shapeObj(MS_SHAPE_POLYGON)
        poly_line = lineObj()
        for xy in feature['coords']:
            p = pointObj(xy[0], xy[1])
            poly_line.add(p)
        poly_shp.add(poly_line)                    
        poly_shp.index = self.shape_index
        if feature_id in self.selected:
            poly_shp.classindex = 1
        self.ms_layer.addFeature(poly_shp)
        if not feature_id:
            feature_id = str(self.shape_index)
        self.features[feature_id] = feature
        self.shape_index += 1


class CircleDLayer(DLayer):
    """
    A circle-specialized DLayer subclass.
    """

    def __init__(self, name, dmap):
        """
        CircleDLayer constructor.

        @type name: str
        @param name: DLayer's name.
        @type dmap: dracones.DMap
        @param dmap: The DMap parent object.
        """
        super(CircleDLayer, self).__init__(name, dmap)

    # very important that the caller performs with sorted feature_id's, because
    # the shape_indexes must start at zero
    def addFeature(self, feature, feature_id = None):
        """
        Add a circle feature.

        @type feature: dict: {gx:float, gy:float, rad:float}
        @param feature: The geographic coordinates of the feature.
        @type feature_id: str | int
        @param feature_id: If the feature has an id.
        """
        if feature_id: feature_id = str(feature_id)
        # todo: assert feature structure
        circle_shp = shapeObj(MS_SHAPE_LINE)
        p1 = pointObj(feature['gx'] - feature['rad'], feature['gy'] + feature['rad'])
        p2 = pointObj(feature['gx'] + feature['rad'], feature['gy'] - feature['rad'])
        line = lineObj()
        line.add(p1)
        line.add(p2)
        circle_shp.add(line)
        if feature_id is not None:
            circle_shp.index = int(feature_id)
        else:
            circle_shp.index = self.shape_index
        if feature_id in self.selected:
            circle_shp.classindex = 1
        self.ms_layer.addFeature(circle_shp)
        if feature_id is None:
            feature_id = str(self.shape_index)
        self.features[feature_id] = feature
        #self.shape_index += 1
        self.shape_index = int(feature_id) + 1

    def drawFeature(self, x, y, rad = 1000):
        """
        Calls addFeature with geographic x/y coords, default radius of 1000.

        @type x: float
        @param x: x coord.
        @type y: float
        @param y: y coord.
        @type rad: float
        @param rad: Circle radius.
        """
        p = pix2geo(self.dmap, x, y)
        self.addFeature({'gx':p.x, 'gy':p.y, 'rad':rad, 'is_sel':False})


class LineDLayer(DLayer):
    """
    A line-specialized DLayer subclass.
    """

    def __init__(self, name, dmap):
        """
        LineDLayer constructor.

        @type name: str
        @param name: DLayer's name.
        @type dmap: dracones.DMap
        @param dmap: The DMap parent object.
        """
        super(LineDLayer, self).__init__(name, dmap)


    def addFeature(self, feature, feature_id = None):
        """
        Add a line feature.

        @type feature: dict: {gx0:float, gy0:float, gx1:float, gy1:float}
        @param feature: The geographic coordinates of the feature.
        @type feature_id: str | int
        @param feature_id: If the feature has an id.
        """
        if feature_id: feature_id = str(feature_id)
        # todo: assert feature structure
        line_shp = shapeObj(MS_SHAPE_LINE)
        line = lineObj()
        p0 = pointObj(feature['gx0'], feature['gy0'])
        line.add(p0)
        p1 = pointObj(feature['gx1'], feature['gy1'])
        line.add(p1)
        line_shp.add(line)                    
        line_shp.index = self.shape_index
        if feature_id in self.selected:
            line_shp.classindex = 1
        self.ms_layer.addFeature(line_shp)
        if not feature_id:
            feature_id = str(self.shape_index)
        self.features[feature_id] = feature
        self.shape_index += 1


    def drawLine(self, x0, y0, x1, y1, from_pixel_coords = True):
        """
        Add a line feature, from coords in geo/pixel coords.

        @type from_pixel_coords: bool
        @param from_pixel_coords: If the input coords are from pixel, they will get converted to geo.
        @param x0, y0, x1, y1: (float) Line coords.
        """
        if from_pixel_coords:
            p0 = pix2geo(self.dmap, x0, y0)
            p1 = pix2geo(self.dmap, x1, y1)
        else:
            p0 = pointObj(x0, y0)
            p1 = pointObj(x1, y1)
        self.addFeature({'gx0':p0.x, 'gy0':p0.y, 'gx1':p1.x, 'gy1':p1.y, 'is_sel':False})
        
        
class DMap(mapObj):
    """
    Dracones encapsulation of a MS map object.    
    """

    def __init__(self, sess, mid, use_viewport_geom = False):
        """
        DMap constructor.

        @type sess: session object
        @param sess: session object.
        @type mid: str
        @param mid: main identifier: map widget ID
        @type use_viewport_geom: bool
        @param use_viewport_geom: Only False for the export function.
        """
        self.mid = mid
        self.sess = sess
        self.sess_mid = sess[mid]
        self.app = sess[mid]['app']
        map_file = "%s/%s.map" % (os.path.abspath(dconf[self.app]['mapfile_path']), sess[mid]['map'])
        super(DMap, self).__init__(map_file)
        if use_viewport_geom:
            self.map_size_rel_to_vp = 1            
        else:
            self.map_size_rel_to_vp = sess[mid]['msvp']
        p = pointObj(self.map_size_rel_to_vp * sess[mid]['mvpw'] / 2, self.map_size_rel_to_vp * sess[mid]['mvph'] / 2)
        self.setSize(self.map_size_rel_to_vp * sess[mid]['mvpw'], self.map_size_rel_to_vp * sess[mid]['mvph'])
        self.zoomPoint(-self.map_size_rel_to_vp, p, self.width, self.height, self.extent, None)
        self.dlayers = {} # 'dlayer_name' -> DLayer object
        self.groups = {} # dlayer group name -> [dlayer names]
        for i in range(self.numlayers):
            ms_layer = self.getLayer(i)            
            dlayer = createDLayerInstance(ms_layer.name, self)
            self.dlayers[ms_layer.name] = dlayer
            if dlayer.group:
                self.groups.setdefault(dlayer.group, []).append(ms_layer.name)


    def pan(self, dir):
        """
        Map panning in four directions.

        @type dir: 'right' | 'left' | 'up' | 'down'
        @param dir: The panning direction.
        """

        # move by (vp_dim * hnvp) - 1/2 vp_dim in dir
        hnvp = (self.map_size_rel_to_vp - 1) / 2
        x_disp = ((self.extent.maxx - self.extent.minx) / self.map_size_rel_to_vp) * (hnvp - 0.5)
        y_disp = ((self.extent.maxy - self.extent.miny) / self.map_size_rel_to_vp) * (hnvp - 0.5)
        
        if dir == 'right':
            self.setExtent(self.extent.minx + x_disp, self.extent.miny, self.extent.maxx + x_disp, self.extent.maxy)
        elif dir == 'left':
            self.setExtent(self.extent.minx - x_disp, self.extent.miny, self.extent.maxx - x_disp, self.extent.maxy)
        elif dir == 'up':
            self.setExtent(self.extent.minx, self.extent.miny + y_disp, self.extent.maxx, self.extent.maxy + y_disp)
        elif dir == 'down':
            self.setExtent(self.extent.minx, self.extent.miny - y_disp, self.extent.maxx, self.extent.maxy - y_disp)
        else:
            assert False


    def zoom(self, x, y, w, h, mode, zs):
        """
        Map +/-, point/box zoom.

        @param x, y, w, h: Pixel/map coords/dims.
        @type mode: 'in' | 'out'
        @param mode: Zoom mode: 'in' | 'out'.
        @type zs: int
        @param zs: zoom size.
        """
        if w and h: # rectangle zoom
            # Confusing rect handling, depending on the MS version
            hnvp = (self.map_size_rel_to_vp - 1) / 2
            if msGetVersionInt() >= 50600:
                rect = rectObj(x, y, x + w, y + h)
                if msGetVersionInt() >= 50602:
                    rect.miny += (hnvp * h)
                    rect.maxy -= (hnvp * h)
                else:
                    rect.miny -= (hnvp * h)
                    rect.maxy += (hnvp * h)                    
            else:
                # Note the additional param (1)
                rect = rectObj(x, y + h, x + w, y, 1)
                rect.miny += (hnvp * h)
                rect.maxy -= (hnvp * h)
            rect.minx -= (hnvp * w)
            rect.maxx += (hnvp * w)
            self.zoomRectangle(rect, self.width, self.height, self.extent, None)
                               
        else: # point zoom
            if not zs:
                zoom_factor = 1
            else:
                if mode == 'in': zoom_factor = zs
                else: zoom_factor = -zs
            p = pointObj(float(x), float(y))
            self.zoomPoint(zoom_factor, p, self.width, self.height, self.extent, None)
                                            

    def setExtentFromDict(self, xt):
        """
        Sets the extent from rectObj dict.

        @type xt: dict: {minx:float, maxx:float, miny:float, maxy:float}
        @param xt: Extent as a dict.
        """
        self.extent.minx = xt['minx']
        self.extent.maxx = xt['maxx']
        self.extent.miny = xt['miny']
        self.extent.maxy = xt['maxy']


    # perform selection only if the layer is ON
    def select(self, dlayers, x, y, w = 0, h = 0, select_mode = 'reset'):
        """
        Performs a point or box selection on a set of dlayers, if their status is MS_ON.

        @type dlayers: list
        @param dlayers: List of dlayers on which to perform the selection.
        @param x, y, w, h: Selection coords in map/pixel coords.
        @type select_mode: str 
        @param select_mode: How selection is to be performed on a DLayer: "reset" (default) will unselect all features before selecting new ones, 
                            "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
        """
        if not isinstance(dlayers, list): dlayers = [dlayers]
        selection_dlayers = []
        for dlayer_name in dlayers:
            if dlayer_name in self.groups: # if dlayer_name is the name of a group
                for dlayer_name_in_grp in self.groups[dlayer_name]:
                    if dlayer_name_in_grp in self.dlayers and self.dlayers[dlayer_name_in_grp].isActive():
                        selection_dlayers.append(dlayer_name_in_grp)
            elif dlayer_name in self.dlayers and self.dlayers[dlayer_name].isActive():
                selection_dlayers.append(dlayer_name)

        for dlayer_to_select in selection_dlayers:

            # box select
            if w and h:
                g1 = pix2geo(self, x, y)
                g2 = pix2geo(self, x + w, y)
                g3 = pix2geo(self, x + w, y + h)
                g4 = pix2geo(self, x, y + h)
                self.dlayers[dlayer_to_select].boxSelect(g1, g2, g3, g4, select_mode)
            # point select
            else:
                p = pix2geo(self, x, y)
                self.dlayers[dlayer_to_select].pointSelect(p, select_mode)


    # image filename structure: <app>_<mid>_<map>_<session_id>.<img_type>
    def getImageURL(self):
        """
        Saves the map image and returns its URL.
        @return: map image URL.
        """
        img = self.draw()
        img.imagepath = os.path.abspath(dconf['ms_tmp_path'])
        fn = "%s_%s_%s_%s.%s" % (self.app, self.mid, self.sess_mid['map'], self.sess.session_id, self.imagetype)
        img_url = "%s%s%s" % (dconf['ms_tmp_url'], '' if dconf['ms_tmp_url'].endswith('/') else '/', fn)
        img.save("%s/%s" % (os.path.abspath(dconf['ms_tmp_path']), fn))
        return img_url


    def getDLayer(self, dlayer_name):
        """
        Returns a dlayer by name, throws an exception if not found.
        @type dlayer_name: str
        @param dlayer_name: Name of the requested dlayer.
        """
        assert self.hasDLayer(dlayer_name), 'The %s dlayer is not set in the current session/map' % dlayer_name
        return self.dlayers[dlayer_name]


    def hasDLayer(self, dlayer_name):
        """
        @return: Whether a dlayer is available or not.
        """
        return (dlayer_name in self.dlayers)


    def restoreStateFromSession(self, restore_extent = True):
        """
        Restores the state of all the dlayers found in the session variable.
        @type restore_extent: bool
        @param restore_extent: If False, will stay with map default extent.
        """
        hist_idx = self.sess_mid['history_idx']
        for name, dlayer in self.dlayers.items():
                # important here to pass copies for compound types
                dlayer.restoreState(self.sess_mid['history'][hist_idx]['dlayers'][name]['filtered'][:],
                                    self.sess_mid['history'][hist_idx]['dlayers'][name]['selected'][:],
                                    self.sess_mid['history'][hist_idx]['dlayers'][name]['features'].copy(),
                                    self.sess_mid['history'][hist_idx]['dlayers'][name]['status'])
        xt = self.sess_mid['history'][hist_idx]['extent']
        if restore_extent and xt:
            self.setExtent(xt['minx'], xt['miny'], xt['maxx'], xt['maxy'])
        

    # "inSession" emphasizes the fact that the session var is modified 
    # ..shift history cells..
    def saveStateInSession(self, shift_history_window = True):
        """
        If required, shifts the history forward, and recursively calls the dlayers' saveStateInSession methods.
        @type shift_history_window: bool
        @param shift_history_window: To prevent an operation's resulting state to be stored in session, set to False.
        """
        if shift_history_window:

            # To preserve the forward order of the history items (i.e. an action at position i is "newer" than one at position < i),
            # we need to detect the case where a new action is initiated somewhere in the history before then end (i.e. undo
            # was used, once or more, and then a new action happened). This means that history_idx < history_size-1.
            # The idea is that we will trim the "future part" of the history (i.e. the part to the right of history_idx) and 
            # start from there.
            # Example: a b c d e
            # If we return back to element c, and issue new action f
            # the outcome should be: _ a b c f
            # Note that we must use a special "init" padding for the first element (_), to prevent going back to it.
            # The same mechanism is also used in the client module (for hover items history)
            hist_idx = self.sess_mid['history_idx']
            hist_size = self.sess_mid['history_size']
            if hist_idx != (hist_size - 1):
                prev_hist_cell = copy.deepcopy(self.sess_mid['history'][hist_idx])
                # shift subset of history (0 to history_idx) to the far right (minus 1)
                hist_copy = copy.deepcopy(self.sess_mid['history'])
                for i in range(0, hist_idx + 1):
                    h = hist_size - hist_idx - 2 + i
                    self.sess_mid['history'][h] = hist_copy[i]
                    if i == 0 and h > 0: # special case: prevent going back to previous part of history (using an 'init' item)
                        self.sess_mid['history'][h-1]['init'] = True
                # add new cell at last slot
                self.sess_mid['history'][-1] = newHistoryCell() # add new cell

            # new action is initiated at the end of history: simply append a new cell at the 
            # right, and pop the oldest one at the left
            else:
                prev_hist_cell = copy.deepcopy(self.sess_mid['history'][-1])
                self.sess_mid['history'].append(newHistoryCell()) # add new cell
                self.sess_mid['history'].pop(0) # remove oldest one

            # copy every prev cell element
            for item in prev_hist_cell:
                if item not in ['dlayers', 'extent']:
                    self.sess_mid['history'][-1][item] = prev_hist_cell[item]
            
        self.sess_mid['history_idx'] = (self.sess_mid['history_size'] - 1) # make sure that pointer is to last elem
        self.sess_mid['history'][-1]['extent'] = self.getExtent()
        for name, dlayer in self.dlayers.items():
            dlayer.saveStateInSession()
        

    # map dlayer -> hover_items
    def getHoverItems(self):
        """
        Hover items for the whole map, as a dict with keys as dlayer names, and values as dicts with 'append' (bool)
        and 'items' (list of hover item triplets). If in 'append' mode, the hover items for a given dlayer will not
        replace the previous ones.
        
        @return: Hover items for the whole map (dict: {dlayer: {append: bool, items: [(hover item triplets)]}}).
        """
        map_hover_items = {}
        for name, dlayer in self.dlayers.items():
            if dlayer.hover_items_are_dirty:
                map_hover_items[name] = {'append': dlayer.hover_items_in_append_mode, 'items':dlayer.hover_items}
        return map_hover_items


    def getSelection(self):
        """
        Selection dict for the whole map.

        @return: {dlayer: [..sel IDs], ..}.
        """
        selection_map = {}
        for name, dlayer in self.dlayers.items():
#            if dlayer.selected:
            selection_map[name] = dlayer.selected
        return selection_map
    

    def getExtent(self):
        """
        @return: The extent as a Python dict.
        """
        return rectObjToDict(self.extent)


    # 'what' is 'selected' or 'all'
    def clearDLayer(self, dlayer_name, what = 'all'):
        """
        Clears a dlayer with respecto to certain item types: selected,
        features, filtered, all.

        @type dlayer_name: str
        @param dlayer_name: Name of the cleared dlayer.
        @type what: 'selected', 'features', 'filtered', 'all'
        @param what: Target attribute for clear.
        """
        if dlayer_name in self.groups: # clear all members of group if dlayer_name is the name of a group
            for dlayer_name_grp in self.groups[dlayer_name]:
                if not self.hasDLayer(dlayer_name_grp) or self.dlayers[dlayer_name_grp].getStatus() != MS_ON: 
                    continue
                if what in ['selected', 'all']:
                    self.dlayers[dlayer_name_grp].clearSelected()
                if what in ['features', 'all']:
                    self.dlayers[dlayer_name_grp].clearFeatures()
                    self.dlayers[dlayer_name_grp].hover_items_are_dirty = True # to have them reset
                if what in ['filtered', 'all']:
                    self.dlayers[dlayer_name_grp].setFilter([])
                    self.dlayers[dlayer_name_grp].hover_items_are_dirty = True # to have them reset
        else:
            if not self.hasDLayer(dlayer_name) or self.dlayers[dlayer_name].getStatus() != MS_ON: return
            if what in ['selected', 'all']:
                self.dlayers[dlayer_name].clearSelected()
            if what in ['features', 'all']:
                self.dlayers[dlayer_name].clearFeatures()
                self.dlayers[dlayer_name].hover_items_are_dirty = True # to have them reset
            if what in ['filtered', 'all']:
                self.dlayers[dlayer_name].setFilter([])
                self.dlayers[dlayer_name].hover_items_are_dirty = True # to have them reset


    def addDLayerFeatures(self):
        """
        Recursively calls addFeatures for all existing dlayers.
        """
        for dlayer in self.dlayers.values():
            dlayer.addFeatures()
        

    def getSelected(self, dlayer_name):
        """
        @type dlayer_name: str
        @param dlayer_name: Name of the dlayer (if group, only the active/displayed ones) for which we want the selected elements.
        @return: List of selected element (IDs) for a given dlayer.
        """
        if dlayer_name in self.groups:
            selected = []
            for dlayer_name_in_grp in self.groups[dlayer_name]:
                if dlayer_name_in_grp in self.dlayers and self.dlayers[dlayer_name_in_grp].isActive():
                    selected.extend(self.dlayers[dlayer_name_in_grp].selected)
            return selected
        else:
            if dlayer_name in self.dlayers:
                return self.dlayers[dlayer_name].selected
            else:
                return []


    def selectFeatures(self, dlayer_name, features, select_mode):
        """
        Wrapper for dlayer.selectFeatures, useful if dlayer is a group.

        @type dlayer_name: str
        @param dlayer_name: Name of dlayer or group of dlayers.
        @type features: list or single item
        @param features: IDs of the selected features.
        @type select_mode: str 
        @param select_mode: How selection is to be performed on a DLayer: "reset" (default) will unselect all features before selecting new ones, 
                            "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
        """
        if dlayer_name in self.groups:
            for dlayer_name_in_grp in self.groups[dlayer_name]:
                if dlayer_name_in_grp in self.dlayers:
                    self.dlayers[dlayer_name_in_grp].selectFeatures(features, select_mode)
        else:
            if dlayer_name in self.dlayers:
                self.dlayers[dlayer_name].selectFeatures(features, select_mode)


    def getActiveDLayersForGroup(self, group_name):
        """
        @type group_name: str
        @param group_name: Name of dlayer group.
        @return: Active/displayed DLayers that are member of a given group.
        """
        active_dlayers = []
        for dlayer_name_in_grp in self.groups.get(group_name, []):
            if dlayer_name_in_grp in self.dlayers and self.dlayers[dlayer_name_in_grp].isActive():
                active_dlayers.append(dlayer_name_in_grp)
        return active_dlayers


    def setHistoryItem(self, item, value):
        """
        Sets a user-defined history item in the current session's history cell.
        The item gets copied every time the history is shifter, so it can be 
        recalled later, using getHistoryItem. IMPORTANT: This must be called 
        *before* the endDracones call.

        @type item: str
        @param item: Name of the item to retrieve.
        @type value: built-in type
        @param value: Value of the item to set (restricted to built-in types).
        """
        hist_idx = self.sess_mid['history_idx']
        self.sess_mid['history'][hist_idx][item] = copy.deepcopy(value)


    def getHistoryItem(self, item):
        """
        Retrieves a user-defined history item.

        @type item: str
        @param item: Name of the item to retrieve.
        @return: Value of the retrieved item.
        """
        hist_idx = self.sess_mid['history_idx'] - 1
        assert item in self.sess_mid['history'][hist_idx]
        return self.sess_mid['history'][hist_idx][item]
