"""This libray contains a collection of useful plot functions regarding coverage."""

import scipy as sp
import numpy.random as npr
import pysam
import sys
import matplotlib.pyplot as plt
import matplotlib.patches as patches
import math
import pdb

from .highlight import *

def _get_counts(chr_name, start, stop, files, intron_cov, intron_cnt=False, verbose=False, collapsed=True, bins=0):
    """Internal function that queries the bam files and produces the counts"""

    ### PYSAM CIGAR ENCODING
    # M   BAM_CMATCH  0
    # I   BAM_CINS    1
    # D   BAM_CDEL    2
    # N   BAM_CREF_SKIP   3
    # S   BAM_CSOFT_CLIP  4
    # H   BAM_CHARD_CLIP  5
    # P   BAM_CPAD    6
    # =   BAM_CEQUAL  7
    # X   BAM_CDIFF   8

    ### init counts
    counts = sp.zeros((len(files), stop - start + 1))
    intron_counts = sp.zeros((len(files), stop - start + 1))
    intron_list = [dict() for i in range(len(files))]

    for f_i, fn in enumerate(files):
        if verbose:
            print >> sys.stdout, "reading bam %i of %i" % (f_i + 1, len(files))  
        try:
            infile = pysam.Samfile(str(fn), "rb")
        except ValueError:
            print >> sys.stderr, 'Could not load file %s - skipping' % fn
            continue
        c_len = stop - start + 1

        for line in infile.fetch(chr_name, start, stop):
            if line.is_secondary:
                continue
            pos = line.pos
            for o in line.cigar:
                if o[0] in [0, 2, 3]:
                    ### get segment overlap to current region
                    seg_offset = max(0, start - pos)
                    seg_len = o[1] - seg_offset
                    if seg_len > 0:
                        seg_start = max(pos - start, 0)
                        if o[0] in [0, 2]:
                            counts[f_i, seg_start : min(seg_start + seg_len, c_len)] += 1 
                        elif (intron_cov or intron_cnt) and o[0] == 3:
                            if pos >= start and (pos + o[1]) <= stop:
                                if intron_cov:
                                    intron_counts[f_i, seg_start : min(seg_start + seg_len, c_len)] += 1
                                if intron_cnt and (seg_start + seg_len < c_len):
                                    try:
                                        intron_list[f_i][(seg_start, seg_len)] += 1
                                    except KeyError:
                                        intron_list[f_i][(seg_start, seg_len)] = 1
                                        
                if not o[0] in [1, 4, 5]:
                    pos += o[1]
    
    if collapsed:
        counts = sp.sum(counts, axis=0)
        intron_counts = sp.sum(intron_counts, axis=0)
        if intron_cnt:
            for f in range(1, len(files)):
                for intron in intron_list[f]:
                    try:
                        intron_list[0][intron] += intron_list[f][intron]
                    except KeyError:
                        intron_list[0][intron] = intron_list[f][intron]
            intron_list = intron_list[0]
                    
    return (counts, intron_counts, intron_list)

def heatmap_from_bam(chrm, start, stop, files, subsample = 0, verbose = False,
                     bins = None, log = False, ax = None, ymax = 0, outfile = None,
                     frm = 'pdf', xlim = None, title = None, xoff = None, yoff = None,
                     intron_cov = False, cmap=None, col_idx=None):
    """This function takes a list of bam files and a set of coordinates (chrm, start, stop), to 
       plot a coverage heatmap over all files in that region."""

    ### subsampling
    if subsample > 0 and len(files) > subsample:
        npr.seed(23)
        files = sp.array(files)
        files = npr.choice(files, subsample)

    ### augment chromosome name
    #chr_name = 'chr%s' % chrm
    chr_name = chrm

    (counts, intron_counts, intron_list) = _get_counts(chr_name, start, stop, files, intron_cov, verbose=verbose, collapsed=False)

    if ax is None:
        fig = plt.figure(figsize = (10, 4))
        ax = fig.add_subplot(111)
    
    if intron_cov:
        data = intron_counts
    else:
        data = counts
    
    if col_idx is not None:
        data = data[:, col_idx]
    
    if log:
        data = sp.log10(data + 1)

    if cmap is not None:
        ax.matshow(data, cmap=cmap, aspect='auto')
    else:
        ax.matshow(data, aspect='auto')

    if outfile is not None:
        plt.savefig(outfile, dpi=300, format=frm)


def cov_from_segments(gene, seg_counts, edge_counts, edge_idx, ax, sample_idx=None,
                      log=False, cmap_seg=None, cmap_edg=None, xlim=None, grid=False,
                      order='C'):
    """This function takes a gene and its corresponding segment and edge counts to
    produce a coverage overview plot."""

    if sample_idx is None:
        sample_idx = sp.arange(seg_counts.shape[1])

    norm = plt.Normalize(0, sample_idx.shape[0])

    if cmap_seg is None:
        cmap_seg = plt.get_cmap('jet')
    if cmap_edg is None:
        cmap_edg = plt.get_cmap('jet')

    ### iterate over samples
    for ii,i in enumerate(sample_idx):
        ### collect count information and add segment patches
        for j in range(gene.segmentgraph.segments.shape[1]):
            s = gene.segmentgraph.segments[:, j]
            if log:
                counts = sp.log10(seg_counts[j, i] + 1)
            else:
                counts = seg_counts[j, i]
            ax.add_patch(patches.Rectangle((s[0], 0), s[1] - s[0], counts, fill=cmap_seg(norm(ii)),
                         edgecolor='none', alpha=0.5))

        for j in range(edge_idx.shape[0]):
            [s, t] = sp.unravel_index(edge_idx[j], gene.segmentgraph.seg_edges.shape, order=order) 
            if log:
                counts = sp.log10(edge_counts[j, i] + 1)
            else:
                counts = edge_counts[j, i]
            add_intron_patch2(ax, gene.segmentgraph.segments[1, s], gene.segmentgraph.segments[0, t], counts, color=cmap_edg(norm(ii)))

    if xlim is not None:
        ax.set_xlim(xlim)

    ### draw grid
    if grid:
        ax.grid(b=True, which='major', linestyle='--', linewidth=0.2, color='#222222')
        ax.xaxis.grid(False)

    ax.set_ylim([0, ax.get_ylim()[1]])

def cov_from_bam(chrm, start, stop, files, subsample=0, verbose=False,
                 bins=None, log=False, ax=None, ymax=0, outfile=None,
                 frm='pdf', xlim=None, title=None, xoff=None, yoff=None,
                 intron_cov=False, intron_cnt=False, marker_pos=None, col_idx=None,
                 color_cov='blue', color_intron_cov='red', color_intron_edge='green', 
                 grid=False, strand=None, highlight=None, highlight_color='magenta', highlight_label=None,
                 min_intron_cnt=0, return_legend_handle=False, label=None):
    """This function takes a list of bam files and a set of coordinates (chrm, start, stop), to 
       plot a coverage overview of that files in that region."""

    ### subsampling
    if subsample > 0 and len(files) > subsample:
        npr.seed(23)
        files = sp.array(files)
        files = npr.choice(files, subsample)

    ### augment chromosome name
    #chr_name = 'chr%s' % chrm
    chr_name = chrm

    (counts, intron_counts, intron_list) = _get_counts(chr_name, start, stop, files, intron_cov, intron_cnt, verbose, collapsed=True)

    ### get mean counts over all bam files
    counts /= len(files)
    if intron_cov:
        intron_counts /= len(files)
    if intron_cnt: 
        for intron in intron_list:
            intron_list[intron] = math.ceil(intron_list[intron] / float(len(files)))
        if min_intron_cnt > 0:
            intron_list = dict([(x, intron_list[x]) for x in intron_list if intron_list[x] >= min_intron_cnt])
    if col_idx is not None:
        counts = counts[col_idx]
        if intron_cov:
            intron_counts = intron_counts[col_idx]
        if intron_cnt:
            print >> sys.stderr, 'ERROR: column subsetting is currently not implemented for intron edges'
            sys.exit(1)

    ### bin counts according to options
    if bins is None:
        bins = counts.shape[0]
        bin_counts = counts
        bin_intron_counts = intron_counts
        if col_idx is not None:
            counts_x = sp.arange(col_idx.shape[0])
        else:
            counts_x = range(start, stop + 1)
    else:
        if verbose:
            print >> sys.stdout, '... binning counts ...'
        bin_counts = sp.zeros((bins,))
        bin_intron_counts = sp.zeros((bins, ))
        binsize = int(sp.ceil(float(counts.shape[0]) / bins))
        for ii, i in enumerate(xrange(0, counts.shape[0], binsize)):
            bin_counts[ii] = sp.sum(counts[i:min(i + binsize, counts.shape[0] - 1)]) / binsize
            if intron_cov:
                bin_intron_counts[ii] = sp.sum(intron_counts[i:min(i + binsize, intron_counts.shape[0] - 1)]) / binsize
        if col_idx is not None:
            counts_x = sp.linspace(0, col_idx.shape[0], num = bins)
        else:
            counts_x = sp.linspace(start, stop, num = bins)

    ### use log if chosen
    if log:
        bin_counts = sp.log10(bin_counts + 1)
        bin_intron_counts = sp.log10(bin_intron_counts + 1)
        if intron_cnt:
            for intron in intron_list:
                if intron_list[intron] > 0:
                    intron_list[intron] = sp.log10(intron_list[intron] + 1)

    if ax is None:
        fig = plt.figure(figsize = (10, 4))
        ax = fig.add_subplot(111)
    if intron_cov:
        ax.fill_between(counts_x, bin_intron_counts, facecolor=color_intron_cov, edgecolor='none', alpha=0.5)

    ax.fill_between(counts_x, bin_counts, facecolor=color_cov, edgecolor='none', alpha=0.5)
    #ax.set_xticklabels([str(int(x)) for x in sp.linspace(start, stop, num = len(ax.get_xticklabels()))])
    ax.set_xlabel('Position on contig %s' % chrm)

    ### draw strand
    if strand == '+':
        ax.arrow(0.05, 0.9, 0.2, 0, head_width=0.05, head_length=0.02, fc='#cccccc', ec='#cccccc', transform=ax.transAxes)
    elif strand == '-':
        ax.arrow(0.25, 0.9, -0.2, 0, head_width=0.05, head_length=0.02, fc='#cccccc', ec='#cccccc', transform=ax.transAxes)

    ### draw grid
    if grid:
        ax.grid(b=True, which='major', linestyle='--', linewidth=0.2, color='#222222')
        ax.xaxis.grid(False)

    if marker_pos is not None:
        ax.plot(0, marker_pos, 'or')

    if log:
        ax.set_ylabel('Read Coverage (log10)')
    else:
        ax.set_ylabel('Read Coverage')

    if ymax > 0:
        ax.set_ylim([0, ymax])

    if highlight is not None:
        highlight_x(ax, highlight, highlight_color=highlight_color, label=highlight_label) 

    if xlim is not None:
        ax.set_xlim(xlim)

    ylim = ax.get_ylim()
    ax.set_ylim([0, ylim[1]])

    if title is not None:
        ax.set_title(title)

    if xoff:
        ax.axes.get_xaxis().set_visible(False)

    if yoff:
        ax.axes.get_yaxis().set_visible(False)

    if intron_cnt:
        for intron in intron_list:
            add_intron_patch2(ax, start + intron[0], start + intron[1] + intron[0], intron_list[intron], color=color_intron_edge)

    if outfile is not None:
        plt.savefig(outfile, dpi = 1200, format = frm)

    if return_legend_handle:
        if label is not None:
            return patches.Patch(color=color_cov, alpha=0.5, label=label)
        else:
            return patches.Patch(color=color_cov, alpha=0.5, label='Expression')

def add_intron_patch(ax, start, stop, cnt):

    import matplotlib.path as mpath

    Path = mpath.Path
    pdata = [(Path.MOVETO, (start, 0)), \
             (Path.CURVE3, (start + (stop-start)/2, 10)), \
             (Path.CURVE3, (stop, 0)), \
             (Path.MOVETO, (stop, 0)), \
             (Path.CURVE3, (start + (stop-start)/2, 10 + (2*cnt))), \
             (Path.CURVE3, (start, 0)), \
             (Path.CLOSEPOLY, (start, 0)), ]

    codes, verts = zip(*pdata)
    path = mpath.Path(verts, codes)
    patch = patches.PathPatch(path, facecolor='g', alpha=0.5)
    ax.add_patch(patch)

def add_intron_patch2(ax, start, stop, cnt, color='green'):
    ### compute a quadratic function through the three points

    ### we set the first root to 0 and shift only the plotting ...
    x2 = ((stop - start) / 2.0)
    x3 = float(stop - start)

    ### compute coefficients
    #z = float((x1*x1*x2 + x1*x3*x3 + x2*x2*x3) - (x3*x3*x2 + x2*x2*x1 + x1*x1*x3))
    z = float((x2*x2*x3) - (x3*x3*x2))
    if z == 0:
        return

    #a = float(cnt) * (x3 - x1) / z
    #b = float(cnt) * ((x1*x1) - (x3*x3)) / z
    #c = float(cnt) * ((x1*x3*x3) - (x1*x1*x3)) / z
    a = float(cnt) * x3 / z
    b = float(cnt) * (-1*(x3*x3)) / z

    ### get points
    #x = sp.linspace(start, stop, 100)
    x = sp.linspace(0, stop-start, 100)
    #y = (a*x*x) + (b*x) + c
    y = (a*x*x) + (b*x)
    ax.plot(sp.linspace(start, stop, 100), y, '-', color=color)

