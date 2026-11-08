"""Small binding to the system HarfBuzz used by Inkscape, with explicit cleanup."""
import ctypes as c
import os
import studio_runtime
from ctypes.util import find_library
from functools import lru_cache


class Info(c.Structure):
    _fields_=[(key,c.c_uint32) for key in ('codepoint','mask','cluster','var1','var2')]


class Position(c.Structure):
    _fields_=[(key,c.c_int32) for key in ('x_advance','y_advance','x_offset','y_offset')]+[('var',c.c_uint32)]


class Feature(c.Structure):
    _fields_=[(key,c.c_uint32) for key in ('tag','value','start','end')]


@lru_cache(maxsize=1)
def library():
    directory=None
    if os.name=='nt':
        folder=studio_runtime.current().inkscape.parent
        directory=os.add_dll_directory(str(folder))
        name=str(folder/'libharfbuzz-0.dll')
    else:name=find_library('harfbuzz')
    if not name:raise ValueError('The HarfBuzz font shaping library is missing from the Inkscape installation.')
    h=c.CDLL(name)
    h._studio_dll_directory=directory
    signatures={
        'hb_blob_create':([c.c_void_p,c.c_uint,c.c_int,c.c_void_p,c.c_void_p],c.c_void_p),
        'hb_face_create':([c.c_void_p,c.c_uint],c.c_void_p),
        'hb_font_create':([c.c_void_p],c.c_void_p),
        'hb_ot_font_set_funcs':([c.c_void_p],None),
        'hb_font_set_scale':([c.c_void_p,c.c_int,c.c_int],None),
        'hb_buffer_create':([],c.c_void_p),
        'hb_buffer_add_utf8':([c.c_void_p,c.c_char_p,c.c_int,c.c_uint,c.c_int],None),
        'hb_buffer_guess_segment_properties':([c.c_void_p],None),
        'hb_direction_from_string':([c.c_char_p,c.c_int],c.c_int),
        'hb_buffer_set_direction':([c.c_void_p,c.c_int],None),
        'hb_shape':([c.c_void_p,c.c_void_p,c.POINTER(Feature),c.c_uint],None),
        'hb_buffer_get_glyph_infos':([c.c_void_p,c.POINTER(c.c_uint)],c.POINTER(Info)),
        'hb_buffer_get_glyph_positions':([c.c_void_p,c.POINTER(c.c_uint)],c.POINTER(Position)),
    }
    for kind in ('buffer','font','face','blob'):signatures['hb_'+kind+'_destroy']=([c.c_void_p],None)
    for name,(args,result) in signatures.items():
        function=getattr(h,name);function.argtypes=args;function.restype=result
    return h


def shape(raw,text,upem,direction='auto',tracking=False):
    h=library();resources=[]
    try:
        data=c.create_string_buffer(raw);blob=h.hb_blob_create(data,len(raw),0,None,None);resources.append(('blob',blob))
        face=h.hb_face_create(blob,0);resources.append(('face',face))
        font=h.hb_font_create(face);resources.append(('font',font));h.hb_ot_font_set_funcs(font);h.hb_font_set_scale(font,upem,upem)
        buffer=h.hb_buffer_create();resources.append(('buffer',buffer));utf8=text.encode('utf-8')
        h.hb_buffer_add_utf8(buffer,utf8,len(utf8),0,len(utf8));h.hb_buffer_guess_segment_properties(buffer)
        if direction!='auto':h.hb_buffer_set_direction(buffer,h.hb_direction_from_string(direction.encode(),-1))
        features=None
        if tracking:features=(Feature*2)(*[Feature(int.from_bytes(tag,'big'),0,0,0xffffffff) for tag in (b'liga',b'clig')])
        h.hb_shape(font,buffer,features,2 if features is not None else 0)
        count=c.c_uint();infos=h.hb_buffer_get_glyph_infos(buffer,c.byref(count));positions=h.hb_buffer_get_glyph_positions(buffer,c.byref(count))
        if count.value>500:raise ValueError('Use fewer characters in this lettering block.')
        return [{'glyph':infos[i].codepoint,'cluster':infos[i].cluster,
                 **{key:getattr(positions[i],key) for key in ('x_advance','y_advance','x_offset','y_offset')}} for i in range(count.value)]
    finally:
        for kind,value in reversed(resources):
            if value:getattr(h,'hb_'+kind+'_destroy')(value)
