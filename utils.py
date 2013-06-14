# -*- coding: utf-8 -*-
"""
Created on Sat Apr 27 20:08:59 2013

@author: andrewmark
"""
from core import Cell, CellReference, CellArray, GdsImport, Text, Rectangle, Round

import os.path
import math
import numpy as np
import numbers

def split_layers(self, old_layers, new_layer):
    """
    Make two copies of the cell, split according to the layer of the artwork
    
    TODO: Include labels as well
      
    returns a pair of new cells
    """
    
    subA=self.deepcopy(suffix='_SPLITA')
    subB=self.deepcopy(suffix='_SPLITB')

    #identify all art in subA that should be removed        
    blacklist=set()
    deps=subA.get_dependencies(True)
    print 'DEPENDENCY LIST HAS LENGTH: ',len(deps)
    for e in deps:
        if not isinstance(e, (Cell, CellReference, CellArray)):
            if e.layer in old_layers:
                blacklist.add(e)

    #remove references to removed art
    for c in deps:
        if isinstance(c, Cell):
            c.elements=[e for e in c.elements if e not in blacklist]
    
    #clean heirarcy
    subA.prune()
            
    #identify all art in subB that should be removed        
    blacklist=set()
    deps=subB.get_dependencies(True)
    for e in deps:
        if not isinstance(e, (Cell, CellReference, CellArray)):
            if e.layer not in old_layers:
                blacklist.add(e)

    #remove references to removed art and change layer of remaining art
    for c in deps:
        if isinstance(c, Cell):
            c.elements=[e for e in c.elements if e not in blacklist]
        if not isinstance(c, (Cell, CellReference, CellArray)):
            c.layer=new_layer
            
    #clean heirarcy
    subB.prune()
    
    return (subA, subB)


class Wafer_GridStyle(Cell):
    """
    A generic gridded wafer style
    
    """

    #wafer radius (in um)
    wafer_r = None
    
    #the block size in um
    block_size = None    
    
    #the placement of the wafer alignment points
    align_pts = None
    
    def __init__(self, name, cells=None, block_gap=400):
        """Create a wafer with blocks in a gridded scheme
            
            cells: a list of cells that will be tiled to fill the blocks
                   style1 contains 12 blocks, the cells will be cycled until
                   all blocks are filled.
        """
        
        Cell.__init__(self, name)

        self.cells=cells
        self.cell_layers=self._cell_layers()
        self._label=None

        self.edge_gap=block_gap/2.        
        
    def _cell_layers(self):
        cell_layers=set()
        for c in self.cells:
            if isinstance(c, Cell):
                cell_layers |= set(c.get_layers())
            else:
                for s in c:
                    cell_layers |= set(s.get_layers())
        return list(cell_layers)        

    def add_aligment_marks(self):
        #Create Alignment Marks
        styles=['A' if i%2 else 'C' for i in range(len(self.cell_layers))]            
        am = AlignmentMarks(styles, self.cell_layers)
        ver = Verniers()
        mag = 10.

        mblock = Cell('WAFER_ALIGN_BLOCKS')
        mblock.add(am, magnification=mag)
        mblock.add(am, origin=(2300, -870))
        mblock.add(ver, origin=(1700, -1500), magnification=3)
        mblock.add(ver, origin=(2000, -1200))

        for pt in self.align_pts:
            offset=np.array([3000, 2000]) * np.sign(pt)            
            self.add(mblock, origin=pt + offset)

    def add_orientation_text(self):
        #Create Orientation Text
        tblock = Cell('WAFER_ORIENTATION_TEXT')
        for l in self.cell_layers:
            for (t, pt) in self.o_text.iteritems():
                txt=Text(l, t, 1000)
                bbox=txt.bounding_box
                width=np.array([1,0]) * (bbox[1,0]-bbox[0,0])
                offset=width * (-1 if pt[0]<0 else 0)
                txt.translate(np.array(pt) + offset)
                tblock.add(txt)
        self.add(tblock)

    def add_dicing_marks(self):
        """
        Create dicing marks
        """
        
        width=100./2
        r=self.wafer_r
        rng=np.floor(self.wafer_r/self.block_size).astype(int)
        dmarks=Cell('DICING_MARKS')
        for l in self.cell_layers:                
            for x in np.arange(-rng[0], rng[0]+1)*self.block_size[0]:
                y=np.sqrt(r**2-x**2)
                vm=Rectangle(l, (x-width, y), (x+width, -y))
                dmarks.add(vm)
            
            for y in np.arange(-rng[1], rng[1]+1)*self.block_size[1]:
                x=np.sqrt(r**2-y**2)
                hm=Rectangle(l, (x, y-width), (-x, y+width))
                dmarks.add(hm)
        self.add(dmarks)

    def add_wafer_outline(self):        
        """
        Create Wafer Outline
        """
        outline=Cell('WAFER_OUTLINE')
        for l in self.cell_layers:
            outline.add(Round(l, (0,0), self.wafer_r, self.wafer_r-10))
        self.add(outline)

    def add_blocks(self):
        #Create Blocks
        for (i, pt) in enumerate(self.block_pts):
            cell=self.cells[i % len(self.cells)]

            if isinstance(cell, Cell):
                cell_name=('BLOCK%02d_'%(i))+cell.name
                block=Block(cell_name, cell, self.block_size, edge_gap=self.edge_gap)
            else:
                cell_name=('BLOCK%02d_'%(i))+cell[0].name
                block=RangeBlock_1D(cell_name, cell, self.block_size, edge_gap=self.edge_gap)

            origin = pt*self.block_size
            self.add(block, origin=origin)

    def _place_blocks(self):
        """
        Create the list of valid block sites
        """        
        ind_max=np.floor(self.wafer_r/self.block_size).astype(int)

        self.block_pts=[]        
        for x in range(-ind_max[0], ind_max[0]):
            for y in range(-ind_max[1], ind_max[1]):
                origin=np.array([x,y])
                flag=True
                for corner in np.array([[0,0], [1,0], [1,1], [0,1]]):
                    lsq=(((origin+corner)*self.block_size)**2).sum()
                    if lsq > self.wafer_r**2:
                        flag=False
                        break
                
                if flag:
                    self.block_pts.append([x,y])
        
        
    def add_label(self, label):
        #Create Label
        if self._label is None:
            self._label=Cell(self.name+'_LABEL')
            self.add(self._label)
        else:
            self._label.elements=[]
        
        for l in self._cell_layers():
            txt=Text(l, label, 1000)
            bbox=txt.bounding_box
            offset=np.array([0,2]) * self.block_size - bbox[0] + 200
            txt.translate(offset)        
            self._label.add(txt)

class Wafer_Style1(Wafer_GridStyle):
    """
    A 2" wafer divided into 10mmx10mm squares
    """
    def __init__(self, name, cells=None, block_gap=400):
        
        #wafer radius (in um)
        self.wafer_r = 25.5e3
        
        #the block size in um
        self.block_size=np.array([10e3, 10e3])    
        
        #the placement of the wafer alignment points
        self.align_pts=np.array([[1, 1],
                            [-1,1],
                            [-1,-1],
                            [1,-1]])*1e4
        
        self.o_text={'UPPER RIGHT':(1.05e4, 1.4e4), 'UPPER LEFT':(-1.05e4,1.4e4),
              'LOWER LEFT':(-1.05e4,-1.5e4), 'LOWER RIGHT':(1.05e4,-1.5e4)}

        Wafer_GridStyle.__init__(self, name, cells, block_gap)

        self._place_blocks()        

        self.add_aligment_marks()
        self.add_orientation_text()
        self.add_dicing_marks()
        self.add_wafer_outline()
        self.add_blocks()


class Wafer_Style2(Wafer_GridStyle):
    """
    A 2" wafer divided into 5mmx5mm squares
    """
    def __init__(self, name, cells=None, block_gap=400):
        
        #wafer radius (in um)
        self.wafer_r = 25.5e3
        
        #the block size in um
        self.block_size=np.array([5e3, 5e3])    
        
        #the placement of the wafer alignment points
        self.align_pts=np.array([[1,1],
                            [-1,1],
                            [-1,-1],
                            [1,-1]])*1e4

        self.o_text={'UPPER RIGHT':(1.05e4, 1.4e4), 'UPPER LEFT':(-1.05e4,1.4e4),
              'LOWER LEFT':(-1.05e4,-1.5e4), 'LOWER RIGHT':(1.05e4,-1.5e4)}


        Wafer_GridStyle.__init__(self, name, cells, block_gap)

        self._place_blocks() 
        blacklist=[[2,2], [2,3], [3,2], [2,-3], [2, -4], [3, -3],
                   [-3,2], [-3,3], [-4,2], [-3,-3], [-3,-4], [-4,-3]]
        new_pts=[]
        for pt in self.block_pts:
            if pt not in blacklist:
                new_pts.append(pt)
        self.block_pts=new_pts

        self.add_aligment_marks()
        self.add_orientation_text()
        self.add_dicing_marks()
        self.add_wafer_outline()
        self.add_blocks()
 
    
class Block(Cell):
    """
    Creates a block section
    """
    def __init__(self, name, cell, size,
                 spacing=None, edge_gap=0,
                 **kwargs):
        """
        Creates a rectangular block with alignment marks, label, and many copies of the cell        
        
        
        cell: the cell to tile
        size: the width and height in physical units of the block
        edge_gap: how much space to leave around the perimeter of the block
        """

        Cell.__init__(self, name)
        size=np.asarray(size)
        cell_layers=cell.get_layers()

        #Create alignment marks
        styles=['A' if i%2 else 'C' for i in range(len(cell_layers))]            
        am=AlignmentMarks(styles, cell_layers)
        ver=Verniers()
        for e in ver.elements:
            e.translate((310,-150))
            am.add(e)
        am_bbox=am.bounding_box
        am_size=np.array([am_bbox[1,0]-am_bbox[0,0], am_bbox[1,1]-am_bbox[0,1]])

        sp=size - am_size - edge_gap
        self.add(CellArray(am, 2, 1, sp, -am_bbox[0]+0.5*edge_gap))
        
        #Create text
        for l in cell_layers:
            print 'Text:',cell.name
            text=Text(l, cell.name, 150, (am_size[0]+edge_gap, +edge_gap))
            bbox=text.bounding_box
            t_width = bbox[1,0]-bbox[0,0]
            self.add(text)        
        
        #Pattern reference cell                
        if spacing is None:
            bbox = cell.bounding_box
            corner=bbox[0]  
            bbox = np.array([bbox[1][0]-bbox[0][0], bbox[1][1]-bbox[0][1]])          
            spacing= bbox*(1.2)        

        # the tiled area consists of three regions:
        # the central section below and above the alignment marks
        # the top section between the two alignement marks
        # the bottom section between the two alignemnt marks
        
        self.N=0
        #The space to leave between the left edge of the block and the
        #left edge of the bottom patterned area
 
        #The space to leave between the bottom of the block and the bottom
        #of the centre patterned area
        #centre section
        cols=np.floor((size[0]-2*edge_gap)/spacing[0])
        rows=np.floor((size[1]-am_size[1]-2*edge_gap)/spacing[1])       

        origin = np.ceil((am_size[1])/spacing[1])\
                    * spacing * np.array([0,1]) + edge_gap - corner

#        origin=np.array([0, am_size[1]])+edge_gap-corner
        ar=CellArray(cell, cols, rows, spacing, origin, **kwargs)
        self.add(ar)
        self.N+=rows*cols

        #bottom section        
        cols=np.ceil((size[0]-2*am_size[0]-t_width-2*edge_gap)/spacing[0])
        rows=np.ceil(am_size[1]/spacing[1])       
#        origin=np.array([am_size[0]+t_width, 0])

        origin = np.ceil((am_size[0]+t_width)/spacing[0])\
                    * spacing * np.array([1,0]) + edge_gap - corner


        ar=CellArray(cell, cols, rows, spacing, origin, **kwargs)
        self.add(ar)
        self.N+=rows*cols

class RangeBlock_1D(Cell):
    """
    Creates a block section for which the the artwork in cols varies
    """
    def __init__(self, name, cells, size, edge_gap=0,
                 **kwargs):
        """
        Creates a rectangular block with alignment marks, label, and many copies of the cell        
        
        
        cells: a list of cells to tile  
        size: the width and height in physical units of the block
        edge_gap: how much space to leave around the perimeter of the block
        """

        Cell.__init__(self, name)
        size=np.asarray(size)
        cell_layers=set()
        for c in cells:
            cell_layers |= set(c.get_layers())
        cell_layers=list(cell_layers)

        #Create alignment marks
        styles=['A' if i%2 else 'C' for i in range(len(cell_layers))]            
        am=AlignmentMarks(styles, cell_layers)
        ver=Verniers()
        for e in ver.elements:
            e.translate((310,-150))
            am.add(e)
        am_bbox=am.bounding_box
        am_size=np.array([am_bbox[1,0]-am_bbox[0,0], am_bbox[1,1]-am_bbox[0,1]])

        sp=size - am_size - edge_gap
        self.add(CellArray(am, 2, 1, sp, -am_bbox[0]+0.5*edge_gap))
        
        #Create text
        for l in cell_layers:
            print 'Text:',cells[0].name
            text=Text(l, cells[0].name, 150, (am_size[0]+edge_gap, +edge_gap))
            bbox=text.bounding_box
            t_width = bbox[1,0]-bbox[0,0]
            self.add(text)        

                
        #Pattern reference cells                

        spacings, corners, widths=[],[],[]        
        for c in cells:
            bbox=c.bounding_box
            corners.append(bbox[0])
            bbox = np.array([bbox[1][0]-bbox[0][0], bbox[1][1]-bbox[0][1]])          
            spacings.append(bbox*1.2)
            widths.append((bbox*1.2)[0])

        # the tiled area consists of three regions:
        # the central section below and above the alignment marks
        # the top section between the two alignement marks
        # the bottom section between the two alignemnt marks
        
        self.N=0
        #The space to leave between the left edge of the block and the
        #left edge of the bottom patterned area
 
        #The space to leave between the bottom of the block and the bottom
        #of the centre patterned area
        #centre section

        origin = edge_gap * np.array([1,1])        

        n_cols=_divide_cols(size[0]-2*edge_gap, widths)

        for (c, w, n, s, cr) in zip(cells, widths, n_cols, spacings, corners):
            if (origin[0]<(am_size[0]+t_width)) or ((origin[0]+n*s[0]) > (size[0]-am_size[0])):
                origin[1]=am_size[1]+edge_gap
                height=size[1]-2*edge_gap-am_size[1]
            else:             
                origin[1]=edge_gap
                height=size[1]-2*edge_gap
            
            rows=np.floor(height/s[1])       
            ar=CellArray(c, n, rows, s, origin-cr, **kwargs)
            self.add(ar)
            self.N+=rows*n
            origin += s[0] * n *np.array([1,0])


def _divide_cols(l, widths):
    """
    Attempt to evenly divide the number of cols.
    
    Try to ensure that:
        -every type has at least one column
        -types have roughly the same number of columns
        -the array takes up as much width as possible
    """        

    widths=np.array(widths)

    n_avg= np.floor(l / widths.sum())

    ns=n_avg * np.ones(len(widths))
    
    excess=l-(ns*widths).sum()
    
    min_w=widths.min()

    while excess>min_w:
        for (i,w) in enumerate(widths):
            if w<excess:
                ns[i]+=1
                excess-=w

    return ns

class RollEdge(Cell):
    
    """
    Create a row of tension strips to define a rolled edge.

    """    
    
    def __init__(self, layer, start, end, size, gap, align='center'):
        """
        
        Params:
            -layer: the layer to add the edge to
            -start: the starting vector for the strips
            -end:
            -size:
            -gap:
            -align: string indicating how to align the strips relative
                    center/top/bottom to the start-end line
        
        """
        Cell.__init__(self, 'EDGE')

        self.start=np.array(start)
        self.end=np.array(end)
        self.size=np.array(size)
        self.gap=gap
        self.align=align

        self.subcell=Cell(self.name+'_SUB')

        box=Rectangle(layer, (0,0), self.size)                    
        if align.lower()=='bottom':
            pass
        elif align.lower()=='top':
            box.translate((0, -self.size[1]))
        elif align.lower()=='center':
            box.translate((0, -self.size[1]/2))        
        else:
            raise ValueError('Align parameter must be one of bottom/top/center')
        self.subcell.add(box)

        t_width=size[0]+gap
        spacing=np.array((t_width, 1))
        
        v=self.end-self.start
        l=np.sqrt(np.dot(v,v))        
        cols=np.floor(l/t_width)    
        rotation=math.atan2(v[1], v[0])*180/np.pi

        self.add(CellArray(self.subcell, cols, 1, spacing, start, rotation))
        

def AlignmentMarks(styles, layers=1):
    """

    styles be a string, or a list of strings indicating the style of mark desired
    layers can be an integer or a list of integers which indicates on which layer to place the corresponding mark

    A:(layer1):    300 x 300 um
    B:
    C:(layer3): 600x400um
    """

    if isinstance(styles, numbers.Number): styles=[styles]
    if isinstance(layers, numbers.Number):
        layers=[layers]*len(styles)
    else:
        if len(layers)!=len(styles):
            raise ValueError('Styles and layers must have same length.')

    styles_dict={'A':1, 'B':2, 'C':3}

    cell=Cell('CONTACT_ALIGN')

    path,_=os.path.split(__file__)
    fname=os.path.join(path, 'CONTACTALIGN.GDS')
    imp=GdsImport(fname)

    for (s,l) in zip(styles, layers):
        style=styles_dict[s]
        for e in imp['CONTACTALIGN'].elements:
            if e.layer==style:
                new_e=e.copy()
                new_e.layer=l
                cell.add(new_e)

    return cell

def Verniers():
    """
    Returns an instance of a pair of vernier alignment tools
    
    TODO: This should be rewritten to behave like AlignemntMarks

    215 x 203 um
    """
    
    cell=Cell('VERNIERS')

    path,_=os.path.split(__file__)
    fname=os.path.join(path, 'VERNIERS.GDS')
    imp=GdsImport(fname)

    for e in imp['VERNIERS'].elements:
        cell.add(e)

    return cell
