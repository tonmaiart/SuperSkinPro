"""GPU shaders and GL helpers for SuperSkinPro color visualizer (Low-level Utilities)."""

import gpu

# Re-export GPU primitives from interface/utils/gpu_utils.py so core callers
# keep working without change and feature packages can also import from
# interface/utils/ directly.
from ...interface.utils.gpu_utils import (
    GL_POLYGON_OFFSET_FILL,
    gl_polygon_offset,
    gl_enable,
    gl_disable,
    BONE_COLORS,
    get_custom_wire_shader,
    get_custom_point_shader,
)

# ── Shared cache (used by ShaderManager for legacy HUD draw) ──
_cache = {
    "batch_col":    None,
    "batch_wire":   None,
    "batch_unsel":  None,
    "batch_sel":    None,
}

# ── Shared ramp interpolation ──

def interpolate_ramp(stops, t):
    """Map a scalar *t* ∈ [0,1] to an RGB tuple using the given color ramp *stops*.

    *stops* must be a sequence of ``(position, (r, g, b))`` tuples sorted by
    position.  Values outside [0,1] are clamped to the first/last stop.
    Handles empty stops gracefully (returns black).
    """
    if not stops:
        return (0.0, 0.0, 0.0)
    if t <= stops[0][0]:
        return stops[0][1]
    if t >= stops[-1][0]:
        return stops[-1][1]
    for i in range(len(stops) - 1):
        t0, c0 = stops[i]
        t1, c1 = stops[i + 1]
        if t0 <= t <= t1:
            if t1 == t0:
                return c0
            frac = (t - t0) / (t1 - t0)
            return tuple(c0[j] + (c1[j] - c0[j]) * frac for j in range(3))
    return stops[-1][1]


def get_custom_wire_shader():
    global _custom_wire_shader
    if _custom_wire_shader is None:
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant('MAT4', "ModelViewProjectionMatrix")
        info.push_constant('VEC4', "color")
        info.vertex_in(0, 'VEC3', "pos")
        info.fragment_out(0, 'VEC4', "FragColor")
        info.vertex_source(
            "void main() {\n"
            "    gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);\n"
            "    gl_Position.z -= 0.00004 * gl_Position.w;\n"
            "}\n")
        info.fragment_source(
            "void main() {\n"
            "    FragColor = color;\n"
            "}\n")
        _custom_wire_shader = gpu.shader.create_from_info(info)
    return _custom_wire_shader


def get_custom_point_shader():
    global _custom_point_shader
    if _custom_point_shader is None:
        info = gpu.types.GPUShaderCreateInfo()
        info.push_constant('MAT4', "ModelViewProjectionMatrix")
        info.push_constant('VEC4', "color")
        info.vertex_in(0, 'VEC3', "pos")
        info.fragment_out(0, 'VEC4', "FragColor")
        info.vertex_source(
            "void main() {\n"
            "    gl_Position = ModelViewProjectionMatrix * vec4(pos, 1.0);\n"
            "    gl_Position.z -= 0.0002 * gl_Position.w;\n"
            "}\n")
        info.fragment_source(
            "void main() {\n"
            "    vec2 coord = gl_PointCoord - vec2(0.5);\n"
            "    float dist = length(coord);\n"
            "    float alpha_mask = smoothstep(0.5, 0.45, dist);\n"
            "    if (alpha_mask == 0.0) discard;\n"
            "    FragColor = vec4(color.rgb, color.a * alpha_mask);\n"
            "}\n")
        _custom_point_shader = gpu.shader.create_from_info(info)
    return _custom_point_shader


def register(): pass
def unregister(): pass
