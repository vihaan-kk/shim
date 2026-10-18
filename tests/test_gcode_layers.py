"""The G-code layer index behind the printer page's live layer view."""

from tools.printer import gcode_layers

GCODE = b"""G90
M82
G92 E0
;LAYER_CHANGE
;Z:0.2
;TYPE:Skirt/Brim
G1 X0 Y0 E1
G1 X10 Y0 E2
;TYPE:External perimeter
G1 X20 Y20 F1800
G1 X30 Y20 E3
G1 X30 Y30 E4
G1 E3.5
G1 X40 Y40
G1 X50 Y40 E4.5
;LAYER_CHANGE
;Z:0.4
;TYPE:External perimeter
G1 X20 Y20
G1 X30 Y20 E5
"""


def test_layers_offsets_and_outer_wall_paths(tmp_path):
    path = tmp_path / "job.gcode"
    path.write_bytes(GCODE)
    index = gcode_layers.index_layers(path)
    layers = index["layers"]
    assert [layer["z"] for layer in layers] == [0.2, 0.4]
    assert [layer["offset"] for layer in layers] == [GCODE.index(b";LAYER_CHANGE"), GCODE.rindex(b";LAYER_CHANGE")]
    # Brim is not drawn; a retraction and travel split the outer wall into two paths.
    assert layers[0]["paths"] == [[20.0, 20.0, 30.0, 20.0, 30.0, 30.0], [40.0, 40.0, 50.0, 40.0]]
    assert layers[1]["paths"] == [[20.0, 20.0, 30.0, 20.0]]


def test_layer_at_follows_the_file_position(tmp_path):
    path = tmp_path / "job.gcode"
    path.write_bytes(GCODE)
    index = gcode_layers.index_layers(path)
    second = index["layers"][1]["offset"]
    assert gcode_layers.layer_at(index, None) is None
    assert gcode_layers.layer_at(index, 0) is None  # start-up code, before the first layer
    assert gcode_layers.layer_at(index, second - 1) == 1
    assert gcode_layers.layer_at(index, second) == 2
    assert gcode_layers.layer_at(index, len(GCODE)) == 2
