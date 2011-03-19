#  Draoones Web-Mapping Framework
#  ==============================
#
#  http://surveillance.mcgill.ca/dracones
#  Copyright (c) 2009, Christian Jauvin
#  All rights reserved. See LICENSE.txt for BSD license notice

"""
Dracones client/server communication module: basically, all the client
services have their binding here. It also serves as the basis for
Dracones extension functions, that get structured with sequential
calls to beginDracones, endDracones and exitDracones.

Every web-accessible function/service in this module is structured as follow:

@dispatcher.match('/foo', 'GET')
@simple_tb_catcher
def foo(req):
    params, sess, dmap = beginDracones(req)

    # Code to perform operations on the dmap, probably using the params..

    json_out = endDracones(dmap)

    # Put any required additional information in json_out..

    return exitDracones(json_out)
"""

import copy, time, traceback, uuid
from dracones.core import *
from pesto import *
from pesto.session.filesessionmanager import *
from pesto.wsgiutils import *


dispatcher = dispatcher_app()
application = session_middleware(FileSessionManager(dconf['session_path']), cookie_path='/')(dispatcher)
                                 

def catchDraconesErrors(f):
    """
    Minimal middleware to catch any exception, and route it to the
    client, for easier debugging.

    @type f: function
    @param f: the function that will be exception wrapped.
    @return: the wrapped function.
    """

    def new_f(*args):
        try:
            return f(*args)
        except Exception as exc:
            if exc.args and exc.args[0] == 'session_expired':
                return Response(content=[json.dumps({'success': False, 'error': 'session_expired',
                                                     'error_msg': 'Session has expired'})],
                                content_type='application/json')            
            elif exc.args and exc.args[0] == 'missing_mid':
                return Response(content=[json.dumps({'success': False, 'error': 'missing_mid',
                                                     'error_msg': "Missing 'mid' param"})],
                                content_type='application/json')
            tb = traceback.format_exc()
            tb = tb.replace('\n', '<br>')
            return Response(content=[json.dumps({'success':False, 'traceback': tb})],
                            content_type='application/json')
    return new_f


def beginDracones(req, **kw):
    """
    B{First step of any Dracones complete interaction}: session
    checking, parameter extraction, dmap creation and state
    restoration.

    @param req: Pesto request object
    @type restore_extent: keyword arg - bool
    @param restore_extent: If False, the extent will be the map's default.
    @type add_features: keyword arg - bool
    @param add_features: Whether to wait before adding the features: some feature manipulations (selection, clear) must be
                         performed prior this call, so it can be deferred (and must be called manually later).
    @type use_viewport_geom: keyword arg - bool
    @param use_viewport_geom: Only used for map image export.
    @type history_dir: keyword arg - 'undo' | 'redo'
    @param history_dir: Undo/redo.
    @return: (params, sess, dmap) triplet, on which to perform custom operations at will.
    """
    restore_extent = kw.get('restore_extent', True)
    add_features = kw.get('add_features', True)
    use_viewport_geom = kw.get('use_viewport_geom', False)
    history_dir = kw.get('history_dir', None)

    params = req.form
    sess = req.session

    if sess.is_new:
        raise Exception('session_expired')
    elif 'mid' not in params:
        raise Exception('missing_mid')

    mid = params['mid']

    if history_dir == 'undo':
        assert sess[mid]['history_idx'] > 0
        sess[mid]['history_idx'] -= 1
    elif history_dir == 'redo':
        assert sess[mid]['history_idx'] < (sess[mid]['history_size'] - 1)
        sess[mid]['history_idx'] += 1

    dmap = DMap(sess, mid, use_viewport_geom)
    dmap.restoreStateFromSession(restore_extent)
    if add_features:
        dmap.addDLayerFeatures()

    return dmap

def endDracones(dmap, **kw):
    """
    B{Second step of any Dracones complete interaction}: creation of
    the return JSON object containing all the variables required
    by the client, state save in the session.

    @type dmap: DMap
    @param dmap: The dmap returned by the previous call to beginDracones.

    @type shift_history_window: keyword arg - bool
    @param shift_history_window: If an operation is not to be recorded in the session, the history window must not be shifted.
    @type update_session: keyword arg - bool
    @param update_session: Whether to update the session or not (for instance, when going back/forward in the history, this is needed).
    @return: json_out JSON dict, containing all the variables required by the client, and that can be modified
             between the return of this call and the final call to exitDracones.
    """
    shift_history_window = kw.get('shift_history_window', True)
    update_session = kw.get('update_session', True)

    json_out = {'success': True}
    json_out['extent'] = dmap.getExtent()
    json_out['hover'] = dmap.getHoverItems()
    json_out['selection'] = dmap.getSelection()
    json_out['map_img_url'] = dmap.getImageURL() 
    if update_session:
        dmap.saveStateInSession(shift_history_window)
    dmap.sess.save()

    json_out['can_undo'] = dmap.sess_mid['history_idx'] > 0 and ('init' not in dmap.sess_mid['history'][dmap.sess_mid['history_idx']-1])
    json_out['can_redo'] = dmap.sess_mid['history_idx'] < (dmap.sess_mid['history_size'] - 1)
    json_out['history_idx'] = dmap.sess_mid['history_idx']
    json_out['shift_history_window'] = shift_history_window if update_session else False
    return json_out

def exitDracones(json_out):
    """
    B{Last step of any Dracones complete interaction}: the response
    sent back to the client.  This function is decoupled for the
    only purpose of letting custom code add some stuff to the
    json_out variable, returned by the previous call to
    endDracones, before it gets returned.
    @type json_out: JSON dict
    @param json_out: the json_out returned by the previous call to endDracones, and possibly modified by custom code.
    @return: Pesto Response object, back to the browser.
    """
    return Response(content=[json.dumps(json_out)], content_type='application/json')


@dispatcher.match('/init', 'GET')
@catchDraconesErrors
def init(req):
    """
    Mandatory first client call: set up the session object, with all the required parameters and return a unique id for this map widget (mid).

    @param req: Pesto request object.
    @type app: str
    @param app: HTTP GET param - name of the application.
    @type map: str
    @param map: HTTP GET param - MS mapfile.
    @type mvpw: int
    @param mvpw: HTTP GET param - map viewport width (corresponds to the widget div dimensions; underlying map will be bigger than that, see msvp param).
    @type mvph: int
    @param mvph: HTTP GET param - map viewport height (corresponds to the widget div dimensions; underlying map will be bigger than that, see msvp param).
    @type msvp: int
    @param msvp: HTTP GET param - map size relative to the viewport (the viewport dims will be multiplied by this value).
    @type history_size: int
    @param history_size: HTTP GET param - number of history cells kept (nb. of times undo will be allowed, in other words).
    """
    params = req.form
    sess = req.session
    json_out = { 'success' : True }

    # init params
    app = params.get('app', None)
    map_name = params.get('map', None)
    mvpw = int(params.get('mvpw', 0)) # map viewport width
    mvph = int(params.get('mvph', 0)) # map viewport height
    msvp = int(params.get('msvp', 0)) # map size relative to viewport
    history_size = int(params.get('history_size', 1))

    if not app or not map_name or not mvpw or not mvph or not msvp:
         return Response(content_type='application/json',
                         content=[json.dumps({'success' : False, 'error' : 'missing init variables (app, map, mvpw, mvph, msvp)'})])

    mid = str(uuid.uuid4())
    sess[mid] = {'app': app, 'map' : map_name, 'mvpw' : mvpw, 'mvph' : mvph, 'msvp': msvp, 'history_size' : history_size, 'history' : [], 'history_idx' : (history_size - 1) }

    for i in range(history_size):
        hist_cell = newHistoryCell()
        if i < history_size - 1: hist_cell['init'] = True # special markers to make it impossible to go back to these 
        sess[mid]['history'].append(hist_cell)

    dmap = DMap(sess, mid)
    json_out = endDracones(dmap, shift_history_window=False)
    json_out['mid'] = mid
    return exitDracones(json_out)


@dispatcher.match('/fullExtent', 'GET')
@catchDraconesErrors
def fullExtent(req):
    """
    Reset the map initial extent.

    @param req: Pesto request object.
    """
    dmap = beginDracones(req, restore_extent=False)
    return exitDracones(endDracones(dmap))


@dispatcher.match('/pan', 'GET')
@catchDraconesErrors
def pan(req):
    """
    Pan map in one of four directions.

    @param req: Pesto request object.
    @type pan_dir: 'right' | 'left' | 'up' | 'down'
    @param pan_dir: HTTP GET param - the direction in which to pan the map.
    """
    dmap = beginDracones(req)            
    params = req.form
    pan_dir = params['dir']
    dmap.pan(pan_dir)
    json_out = endDracones(dmap, shift_history_window=True) # Not sure if pan steps should be recorded as history items..
    json_out['pan_dir'] = pan_dir
    return exitDracones(json_out)


@dispatcher.match('/zoom', 'GET')
@catchDraconesErrors
def zoom(req):
    """
    Point/box zoom.

    @param req: Pesto request object.
    @type x: int
    @param x: HTTP GET param - x coord (in pixel/map coords).
    @type y: int
    @param y: HTTP GET param - y coord (in pixel/map coords).
    @type w: int
    @param w: HTTP GET param - width of the box zoom (optional, in map pixels).
    @type h: int
    @param h: HTTP GET param - height of the box zoom (optional, in map pixels).
    @type mode: 'in' | 'out'
    @param mode: HTTP GET param - zoom mode, "in" or "out".
    @type zsize: int
    @param zsize: HTTP GET param - zoom size.
    """
    dmap = beginDracones(req)

    # input params
    params = req.form
    x = int(params.get('x'))        
    y = int(params.get('y'))
    w = int(params.get('w', 0)) # if these are zero: point zoom
    h = int(params.get('h', 0))
    mode = params.get('mode', None)
    zsize = int(params.get('zsize', 2))

    dmap.zoom(x, y, w, h, mode, zsize)

    return exitDracones(endDracones(dmap))

# CTRL + left mouse button: box/point action: select or draw)

@dispatcher.match('/action', 'GET')
@catchDraconesErrors
def action(req):
    """
    An I{action} is triggered by the use of CTRL + left mouse
    button: a I{point action} for CTRL + single click, and a I{box
    action} for CTRL + drag. This function can only perform two
    default Dracones actions: select and draw. You can point/box
    select items on multiple layers at once, provided that they have
    CLASSITEM attributes. You can also draw a feature at a particular
    x/y location. B{Note that for the moment, the drawing of an object
    with rectangular coordinates is not supported.}

    @param req: Pesto request object.
    @type x: int
    @param x: HTTP GET param - x coord (in pixel/map coords).
    @type y: int
    @param y: HTTP GET param - y coord (in pixel/map coords).
    @type w: int
    @param w: HTTP GET param - width of the box zoom (optional, in map pixels).
    @type h: int
    @param h: HTTP GET param - height of the box zoom (optional, in map pixels).
    @type action: 'select' | 'draw'
    @param action: HTTP GET param - the action to perform.
    @type select_mode: str 
    @param select_mode: HTTP GET param - how selection is to be performed on a DLayer: "reset" (default) will unselect all features before selecting new ones, 
                                         "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
    @type dlayers: str (items joined by commas)
    @param dlayers: HTTP GET param - list of dlayers on which to perform the action.
    """
    dmap = beginDracones(req, add_features=False) # dont add features, because we may need to clear the

    json_out = {'success': True}                                

    # input params
    params = req.form
    x = int(params.get('x', 0))
    y = int(params.get('y', 0))
    w = int(params.get('w', 0))
    h = int(params.get('h', 0))
    action = params.get('action', None)
    select_mode = params.get('select_mode', 'reset')
    dlayers = params.get('dlayers', None)

    if action == 'select':

        # only significant for custom feature layers
        if select_mode == 'reset':
            for dlayer_name in dlayers.split(',') if dlayers else []:
                dmap.clearDLayer(dlayer_name, 'selected')

        dmap.addDLayerFeatures()
        dmap.select(dlayers.split(',') if dlayers else [], x, y, w, h, select_mode)

    elif action == 'draw':

        dmap.addDLayerFeatures()
        for dlayer_name in dlayers.split(',') if dlayers else []:            
            if dmap.hasDLayer(dlayer_name):
                dmap.dlayers[dlayer_name].drawFeature(x, y)

    else:

        assert False, 'action is not defined'

    return exitDracones(endDracones(dmap))


@dispatcher.match('/setDLayersStatus', 'GET')
@catchDraconesErrors
def setDLayersStatus(req):
    """
    Set dlayers status on/off.

    @param req: Pesto request object.
    @type dlayers_on: str (items joined by commas)
    @param dlayers_on: HTTP GET param - list of dlayers to activate.
    @type dlayers_off: str (items joined by commas)
    @param dlayers_off: HTTP GET param - list of dlayers to desactivate.
    """
    dmap = beginDracones(req)

    params = req.form
    dlayers_on = params.get('dlayers_on', None)
    dlayers_off = params.get('dlayers_off', None)

    # dlayers to turn on
    for dlayer_name in list(set(dlayers_on.split(',') if dlayers_on else [])):
        dmap.dlayers[dlayer_name].setStatus(MS_ON)

    # dlayers to turn off
    for dlayer_name in list(set(dlayers_off.split(',') if dlayers_off else [])):
        dmap.dlayers[dlayer_name].setStatus(MS_OFF)

    return exitDracones(endDracones(dmap))


@dispatcher.match('/clearDLayers', 'GET')
@catchDraconesErrors
def clearDLayers(req):
    """
    Clears dlayers with respect to certain attributes: selected/filtered items,
    features, all.

    @param req: Pesto request object.
    @type what: 'selected' | 'filtered' | 'features' | 'all'
    @param what: HTTP GET param - the items to clear.
    @type dlayers: str (items joined by commas)
    @param dlayers: HTTP GET param - list of dlayers on which to apply the clear.
    """
    dmap = beginDracones(req, add_features=False) # dont add features yet

    params = req.form
    what = params.get('what')
    dlayers_to_clear = params.get('dlayers', None)

    for dlayer_name in list(set(dlayers_to_clear.split(","))) if dlayers_to_clear else []:
        dmap.clearDLayer(dlayer_name, what) # need to remove ref to sess/mid here
    dmap.addDLayerFeatures()

    return exitDracones(endDracones(dmap))


@dispatcher.match('/toggleDLayers', 'GET')
@catchDraconesErrors
def toggleDLayers(req):
    """
    Toggle on/off list of dlayers.
    @param req: Pesto request object.
    @type dlayers: str (items joined by commas)
    @param dlayers: HTTP GET param - list of dlayers to toggle.
    """
    dmap = beginDracones(req)

    params = req.form
    if params.get('dlayers', None): dlayers_to_toggle = list(set(params.get('dlayers').split(",")))
    else: dlayers_to_toggle = []

    # warning: toggled dlayer must have been created by a previous call
    for dlayer_name in dlayers_to_toggle:
        if dmap.dlayers[dlayer_name].getStatus() == MS_ON:
            dmap.dlayers[dlayer_name].setStatus(MS_OFF)
        else:
            dmap.dlayers[dlayer_name].setStatus(MS_ON)

    return exitDracones(endDracones(dmap))


@dispatcher.match('/export', 'GET')
@catchDraconesErrors
def export(req):
    """
    Export an image of the current map.

    @param req: Pesto request object.
    @type vptx: int
    @param vptx: HTTP GET param - viewport horizontal translation, in map/pixel coords.
    @type vpty: int
    @param vpty: HTTP GET param - viewport vertical translation, in map/pixel coords.
    """
    dmap = beginDracones(req, use_viewport_geom=True) 

    # input params
    params = req.form
    vptx = int(params.get('vptx', 0))
    vpty = int(params.get('vpty', 0))

    hist_idx = dmap.sess_mid['history_idx']
    xt = dmap.sess_mid['history'][hist_idx]['extent'].copy()

    # First adjust temp extent to match vp size map
    xvp = (xt['maxx'] - xt['minx']) / dmap.sess_mid['msvp']
    yvp = (xt['maxy'] - xt['miny']) / dmap.sess_mid['msvp']
    hnvp = (dmap.sess_mid['msvp'] - 1) / 2 # half n viewports
    xt['minx'] += (hnvp * xvp)
    xt['maxx'] = xt['minx'] + xvp
    xt['miny'] += (hnvp * yvp)
    xt['maxy'] = xt['miny'] + yvp
    dmap.setExtentFromDict(xt)

    # Then adjust for viewport translation
    disp_geo = pix2geo(dmap, vptx, vpty)
    xd = xt['minx'] - disp_geo.x
    yd = xt['maxy'] - disp_geo.y
    xt['minx'] += xd
    xt['maxx'] += xd
    xt['miny'] += yd
    xt['maxy'] += yd
    dmap.setExtentFromDict(xt)

    img = dmap.draw()
    img.imagepath = os.path.abspath(dconf['ms_tmp_path'])
    # image filename structure: <mapname>_<mid>_<session_id>_EXPORT.<img_type>
    fn = "%s_%s_%s_%s.%s" % (dmap.sess_mid['map'], dmap.app, dmap.sess.session_id, "EXPORT", dmap.imagetype)
    img.save("%s/%s" % (os.path.abspath(dconf['ms_tmp_path']), fn))

    return serve_static_file(req, '%s/%s' % (os.path.abspath(dconf['ms_tmp_path']), fn)).add_headers(
        content_disposition='attachment; filename=%s_%s.%s' % (dmap.app, time.strftime('%Y-%m-%d_%Hh%Mm%Ss'), dmap.imagetype))


@dispatcher.match('/setFeatureVisibility', 'GET')
@catchDraconesErrors
def setFeatureVisibility(req):
    """
    Modifies the visibility status of a single feature item.

    @param req: Pesto request object.
    @type dlayer: str
    @param dlayer: HTTP GET param - the target dlayer.
    @type features: str (items joined by commas)
    @param features: HTTP GET param - the feature IDs to select.
    @type visibles: str ('true'|'false' joined by commas)
    @param visibles: HTTP GET param - visibility status corresponding to each feature.
    @type is_visible: B{str} ('true' | 'false')
    @param is_visible: HTTP GET param - feature visibility status.
    """
    dmap = beginDracones(req, add_features=False) 

    # input params
    params = req.form
    dlayer_name = params.get('dlayer')
    if params.get('features', None): features = list(set(params.get('features', None).split(",")))
    else: features = []
    if params.get('visibles', None): visibles = list(set(params.get('visibles', None).split(",")))
    else: visibles = []

    assert len(features) == len(visibles)

    for i, feature_id in enumerate(features):
        dmap.dlayers[dlayer_name].setFeatureVisibility(feature_id, visibles[i].lower()=='true')

    dmap.addDLayerFeatures()

    return exitDracones(endDracones(dmap))


@dispatcher.match('/selectFeatures', 'GET')
@catchDraconesErrors
def selectFeatures(req):
    """
    Select feature items.

    @param req: Pesto request object.
    @type dlayer: str
    @param dlayer: HTTP GET param - the targer dlayer.
    @type features: str (items joined by commas)
    @param features: HTTP GET param - the feature IDs to select.
    @type select_mode: str 
    @param select_mode: HTTP GET param - how selection is to be performed on a DLayer: "reset" (default) will unselect all features before selecting new ones, 
                                         "toggle" will toggle the selected state of the target items, and "add" will not unselect nor toggle anything before selecting new features.
    """
    dmap = beginDracones(req, add_features=False) 

    # input params
    params = req.form
    dlayer_name = params.get('dlayer')
    if params.get('features', None): features = list(set(params.get('features', None).split(",")))
    else: features = []
    select_mode = params.get('select_mode', 'reset')

    dmap.selectFeatures(dlayer_name, features, select_mode)

    dmap.addDLayerFeatures()

    return exitDracones(endDracones(dmap))


@dispatcher.match('/history', 'GET')
@catchDraconesErrors
def history(req):
    """
    Navigate the map history (undo/redo).

    @param req: Pesto request object.
    @type direction: 'undo' | 'redo'
    @param direction: HTTP GET param - undo or redo.
    """

    direction = req.form.get('dir', None)
    dmap = beginDracones(req, history_dir=direction)     
    return exitDracones(endDracones(dmap, update_session=False))

