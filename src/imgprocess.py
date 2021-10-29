import os
import glob
import numpy as np
import pandas as pd
from pathlib import Path
import torch
from torchvision import transforms

from PIL import Image
Image.MAX_IMAGE_PIXELS = None

################### CONSTANTS ##################

VISIUM_H_ST = 78  # Visium arrays contain 78 rows (height)
VISIUM_W_ST = 64  # ...each row contains 64 spots (width)

############### HELPER FUNCTIONS ###############

def pseudo_hex_to_oddr(col, row):
	if row % 2 == 0:
		x = col/2
	else:
		x = (col-1)/2
	y = row
	return int(x), int(y)

def oddr_to_pseudo_hex(col, row):
	y_vis = row
	x_vis = col * 2
	if row % 2 == 1:
		x_vis += 1
	return  int(x_vis), int(y_vis)


######## VISIUM ANNOTATION PROCESSING #######

# Convert Loupe annotation files (barcode, AAR pairs) to Splotch annotation files (AARs x spots matrix).
# Splotch does this conversion under the hood -- for now, GridNext expects Splotch formatted inputs.
def to_splotch_annots(loupe_annotations, tpl_files, dest_dir, include_annots=None):
	'''
	Parameters:
	----------
	loupe_annotations: iterable of path
		paths to Loupe annotation files
	tpl_files: iterable of path
		paths to tissue_position_list.csv files output by spaceranger for tissues specified in loupe_annotations.
	dest_dir: path
		directory in which to save Splotch-formatted annotation files.
	include_annots: list of str or None
		ordered list of annotations to include in Splotch files.
		If None, all annotations found across Loupe files will be included in alphanumeric order.
	'''
	
	# If annotations not provided, extract list of all unique annotations across provided files.
	if include_annots is None:
		annot_list = []
		for afile in loupe_annotations:
			adat = pd.read_csv(afile, header=0, sep=',')
			keep_inds = [isinstance(a, str) and len(a) > 0 and a.lower() != 'undefined' for a in adat[adat.columns[1]]]
			annot_list.append(adat[adat.columns[1]][keep_inds])
		include_annots = list(np.unique(np.concatenate(annot_list)))

	for afile, tfile in zip(loupe_annotations, tpl_files):
		annots = pd.read_csv(afile, header=0, sep=",")
		positions = pd.read_csv(tfile, index_col=0, header=None,
			names=["in_tissue", "array_row", "array_col", "pixel_row", "pixel_col"])
		annot_matrix = np.zeros((len(include_annots), len(annots['Barcode'])), dtype=int)

		positions_list = []
		for i,b in enumerate(annots['Barcode']):
			xcoor = positions.loc[b,'array_col']
			ycoor = positions.loc[b,'array_row']
			positions_list.append('%d_%d' % (xcoor, ycoor))

			if annots.iloc[i,1] in include_annots:
				annot_matrix[include_annots.index(annots.iloc[i,1]),i] = 1

		splotch_frame = pd.DataFrame(annot_matrix, index=include_annots, columns=positions_list)
		outfile = os.path.join(dest_dir, Path(afile).name).replace('csv', 'tsv')
		splotch_frame.to_csv(outfile, sep='\t')


######## VISIUM IMAGE PROCESSING ########

# Extracts image patches centered at each Visium spot and returns as a 5D tensor for input to GridNet.
#   (tensor is odd-right indexed, meaning odd-indexed rows should be shifted right to generate hex grid.)
def grid_from_wsi_visium(fullres_imgfile, tissue_positions_listfile, patch_size=256, window_size=256, 
	preprocess_xform=None):
	'''
	Parameters:
	----------
	fullres_imgfile: path
		full-resolution image of tissue on Visium array.
	tissue_positions_listfile: path 
		tissue_positions_list.csv exported by spaceranger, which maps Visium array indices to 
		pixel coordinates in full-resolution image.
	patch_size: tuple of int
		size of image patches in pixels.
	window_size: tuple of int or float
		if different from patch_size, size of patches to be extracted before resizing to patch_size.
		If int, size of image region to be extracted in pixels. If float, fraction of patch_size.
	preprocess_transform: torchvision transform
		preprocessing transform to be applied to image patches extracted from WSI prior to inference.

	Returns:
	---------
	img_tensor: torch.Tensor
		tensor containing odd-right indexed representation of extracted image patches 
		(H_VISIUM, W_VISIUM, 3, patch_size, patch_size)
	'''
	img = np.array(Image.open(fullres_imgfile))
	ydim, xdim = img.shape[:2]

	if window_size is None:
		w = patch_size
	elif isinstance(window_size, float):
		w = int(window_size * xdim)
	elif isinstance(window_size, int):
		w = window_size
	else:
		raise ValueError("Window size must be a float or int")

	# Pad image such that no patches extend beyond image boundaries
	img = np.pad(img, pad_width=[(w//2, w//2), (w//2, w//2), (0,0)], mode='edge')

	df = pd.read_csv(tissue_positions_listfile, sep=",", header=None, 
		names=['barcode', 'in_tissue', 'array_row', 'array_col', 'px_row', 'px_col'])
	# Only consider spots that are within the tissue area.
	df = df[df['in_tissue']==1]

	# Create a 5D tensor to store the image array, then populate with patches
	# extracted from the full-resolution image.
	img_tensor = torch.zeros((VISIUM_H_ST, VISIUM_W_ST, 3, patch_size, patch_size))
	for i in range(len(df)):
		row = df.iloc[i]
		x_ind, y_ind = pseudo_hex_to_oddr(row['array_col'], row['array_row'])
		x_px, y_px = df.iloc[i]['px_col'], df.iloc[i]['px_row']

		# Account for image padding
		x_px += w//2
		y_px += w//2

		patch = img[(y_px-w//2):(y_px+w//2), (x_px-w//2):(x_px+w//2)]
		patch = np.array(Image.fromarray(patch).resize((patch_size, patch_size)))
		
		patch = torch.from_numpy(patch).permute(2,0,1)
		if preprocess_xform is not None:
			xf = transforms.Compose([
				transforms.ToPILImage(),
				transforms.ToTensor(),
				preprocess_xform
			])
			patch = xf(patch)

		if y_ind >= VISIUM_H_ST or x_ind > VISIUM_W_ST:
			print("Warning: column %d row %d outside bounds of Visium array" % (x_ind, y_ind))
			continue

		img_tensor[y_ind, x_ind] = patch

	return img_tensor.float()

# For a sequence of samples, extracts patches centered around each Visium spot and save as JPG files 
#   in directory structure expected by Dataset classes for use with GridNet
def save_visium_patches(wsi_files, tpl_files, dest_dir, patch_size=256, window_size=None):
	'''
	Parameters:
	-----------
	wsi_files: iterable of path
		paths to WSI files used in Visium pipeline.
	tpl_files: iterable of path
		tissue_positions_list.csv files exported by spaceranger for wsi_files.
	dest_dir: path
		top-level directory in which to save image patch data.
	patch_size: tuple of int
		size of image patches in pixels.
	window_size: tuple of int or float
		if different from patch_size, size of patches to be extracted before resizing to patch_size.
		If int, size of image region to be extracted in pixels. If float, fraction of patch_size.
	'''
	if not os.path.isdir(dest_dir):
		os.mkdir(dest_dir)

	for img_file, tpl_file in zip(wsi_files, tpl_files):
		print("%s : %s ..." % (img_file, tpl_file))

		# Extract name of current tissue
		slide = str(Path(img_file).stem)

		# Generate patch grid tensor (H_ST, W_ST, C, H_p, W_p)
		patch_grid = grid_from_wsi_visium(img_file, tpl_file, patch_size=patch_size, window_size=window_size)

		if not os.path.isdir(os.path.join(dest_dir, "%s" % slide)):
			os.mkdir(os.path.join(dest_dir, "%s" % slide))

		# Save all foreground patches as separate JPG files.
		for oddr_x in range(VISIUM_W_ST):
			for oddr_y in range(VISIUM_H_ST):
				if patch_grid[oddr_y, oddr_x].max() > 0:
					patch = patch_grid[oddr_y, oddr_x]
					patch = np.moveaxis(patch.data.numpy().astype(np.uint8), 0, 2)  # switch to chanels-last

					# Save with Visium indexing to facilitate matching to count data
					x_vis, y_vis = oddr_to_pseudo_hex(oddr_x, oddr_y)
					Image.fromarray(patch).save(
						os.path.join(dest_dir, "%s" % slide, "%d_%d.jpg" % (x_vis, y_vis)), "JPEG")


if __name__ == '__main__':
	#wsi_file = '/Users/adaly/Desktop/Visium/Maynard_ImageData/151510_full_image.tif'
	#tpl_file = '/Users/adaly/Documents/Splotch_projects/Maynard_DLPFC/data/Spaceranger_simulated/151510_tissue_positions_list.csv'
	#res = grid_from_wsi_visium(wsi_file, tpl_file)
	#print(res.max())

	#dest_dir = '/Users/adaly/Documents/Splotch_projects/Maynard_DLPFC/data/maynard_patchdata_oddr/'
	#wsi_files = sorted(glob.glob('/Users/adaly/Desktop/Visium/Maynard_ImageData/*_full_image.tif'))
	#tpl_files = sorted(glob.glob('/Users/adaly/Documents/Splotch_projects/Maynard_DLPFC/data/Spaceranger_simulated/*_tissue_positions_list.csv'))
	#save_visium_patches(wsi_files, tpl_files, dest_dir)

	data_dir = '/mnt/home/adaly/ceph/datasets/BA44/'
	meta = pd.read_csv(os.path.join(data_dir, 'Splotch_Metadata.tsv'), header=0, sep='\t')
	tpl_files = [os.path.join(data_dir, srd + '/outs/spatial/tissue_positions_list.csv') for srd in meta['Spaceranger output']]
	annot_files = [os.path.join(data_dir, afile) for afile in meta['Annotation file']]
	to_splotch_annots(annot_files, tpl_files, os.path.join(data_dir, 'annotations_splotch'))

