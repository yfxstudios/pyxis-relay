"""Pictures of the case with the board inside, for checking by eye: case/out/view-*.png.

  python case/render.py

Needs CadQuery and VTK (VTK comes with CadQuery). Renders off-screen.
"""
import os

import vtk

import case as C
import cadquery as cq

OUT = C.OUT


def polydata(shape, tol=0.1):
    pd = shape.toVtkPolyData(tol, 0.3)          # OCC's mesher, in C++
    n = vtk.vtkPolyDataNormals()
    n.SetInputData(pd)
    n.SetFeatureAngle(35)
    n.Update()
    return n.GetOutput()


def actor(pd, color, opacity=1.0, offset=(0, 0, 0)):
    m = vtk.vtkPolyDataMapper()
    m.SetInputData(pd)
    a = vtk.vtkActor()
    a.SetMapper(m)
    a.GetProperty().SetColor(*color)
    a.GetProperty().SetOpacity(opacity)
    a.SetPosition(*offset)
    return a


def render(actors, name, cam_pos, focal=(60, -50, 12), up=(0, 0, 1), size=(1400, 1000)):
    ren = vtk.vtkRenderer()
    ren.SetBackground(1, 1, 1)
    for a in actors:
        ren.AddActor(a)
    cam = ren.GetActiveCamera()
    cam.SetFocalPoint(*focal)
    cam.SetPosition(*cam_pos)
    cam.SetViewUp(*up)
    ren.ResetCamera()
    cam.Zoom(1.25)
    win = vtk.vtkRenderWindow()
    win.SetOffScreenRendering(1)
    win.AddRenderer(ren)
    win.SetSize(*size)
    win.Render()
    w2i = vtk.vtkWindowToImageFilter()
    w2i.SetInput(win)
    w2i.Update()
    png = vtk.vtkPNGWriter()
    png.SetFileName(os.path.join(OUT, f"view-{name}.png"))
    png.SetInputConnection(w2i.GetOutputPort())
    png.Write()
    print("wrote", f"case/out/view-{name}.png")


def main():
    os.makedirs(OUT, exist_ok=True)
    base, lid = polydata(C.base().val()), polydata(C.lid().val())
    board = polydata(cq.importers.importStep(os.path.join(C.HERE, "ref", "relay-board.step"))
                     .translate((-30.0, 30.0, C.Z_BB)).val(), 0.3)
    grey, blue, green = (0.80, 0.80, 0.83), (0.35, 0.55, 0.85), (0.15, 0.55, 0.25)
    # closed, from the rear-left (Y negative is the rear, y = 100) and the front-right
    render([actor(base, grey), actor(lid, blue), actor(board, green)], "rear", (-80, -260, 160))
    render([actor(base, grey), actor(lid, blue), actor(board, green)], "front", (220, 170, 140))
    # exploded: lid lifted 45 mm, see-through
    render([actor(base, grey), actor(lid, blue, 0.55, (0, 0, 45)), actor(board, green)], "exploded",
           (-120, -240, 230), focal=(60, -50, 30))
    # board in the base, from above
    render([actor(base, grey), actor(board, green)], "base-top", (60, -50, 300), up=(0, 1, 0))
    # lid from underneath (posts, openings)
    render([actor(lid, blue)], "lid-under", (60, -50, -250), up=(0, 1, 0))
    # roof labels, close up, as seen standing at the front
    from PIL import Image
    fine = polydata(C.lid().val(), 0.02)
    render([actor(fine, blue)], "labels", (105, -16, 120), focal=(105, -16, C.Z_TOP), up=(0, -1, 0), size=(4000, 2800))
    path = os.path.join(OUT, "view-labels.png")
    im = Image.open(path)
    w, h = im.size
    im.crop((int(w * 0.17), int(h * 0.62), int(w * 0.33), int(h * 0.84))).save(path)


if __name__ == "__main__":
    main()
