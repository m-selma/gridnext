import pandas as pd
import os
import glob
import shutil

# getting the number of unqiue AAR values from every file 
def get_unique_entries_from_folder(folder_path, col_name):
    unique_entries = set()
    csv_files = glob.glob(os.path.join(folder_path, '*.csv'))
    
    for file_path in csv_files:
        df = pd.read_csv(file_path)
        if col_name in df.columns:
            unique_entries.update(df[col_name].dropna().unique())
    
    return list(unique_entries)

folder_path = r'D:\smarrakchi\Gridnet_UCAN_data\annotations'
col_name = 'AARs'
unique_entries = get_unique_entries_from_folder(folder_path, col_name)
len((unique_entries))

###
# defining AAR list
AARs = ["Muscle: General",
        "Submucosa: General",
        "Submucosa: Lamina Propria",
        "Submucosa: Vessels",
        "Mucosa: Base",
        "Mucosa: Mid",
        "Mucosa: Apex",
        "Mucosa: Cross-Mucosa",
        'Tumor: Undifferentiated',
        'Tumor Stroma: Fibromuscular',
        'Submucosa: Lymphoid Aggregates',
        'Submucosa: Adipose Tissue',
        'Tumor: Transitional',
        'Tumor: Polyps',
        'Tumor Stroma: Immune-infiltrated',
        'Tumor: Glandular', 
        'Tumor: Necrotic'       
        ]

###
# concatenating all muscle types under general muscle 
def replace_muscle_entries(folder_path, col_name, replacements, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    csv_files = glob.glob(os.path.join(folder_path, '*.csv'))
    
    for file_path in csv_files:
        df = pd.read_csv(file_path)
        
        if col_name in df.columns:
            df[col_name] = df[col_name].replace(replacements)
            output_path = os.path.join(output_folder, os.path.basename(file_path))
            df.to_csv(output_path, index=False)
        else:
            print(f"Column '{col_name}' not found in {file_path}. Skipping file.")

folder_path = r'D:\smarrakchi\Gridnet_UCAN_data\annotations_v2'
col_name = 'AARs'
replacements = {
    'Muscle: Inner Layer': 'Muscle: General',
    'Muscle: Outer Layer': 'Muscle: General'
}
output_folder = r'D:\smarrakchi\Gridnet_UCAN_data\annotations_v2_mod'
replace_muscle_entries(folder_path, col_name, replacements, output_folder)

###
# removing all rows that have entries not in the AAR list
def filter_csv_files(folder_path, col_name, valid_values, output_folder):
    if not os.path.exists(output_folder):
        os.makedirs(output_folder)
    
    csv_files = glob.glob(os.path.join(folder_path, '*.csv'))
    
    for file_path in csv_files:
        df = pd.read_csv(file_path)
        
        if col_name in df.columns:
            mask = df.apply(lambda x: x.str.contains(';')) #Check for the presence of ';' in any column
            df_filt = df[~mask.any(axis=1)] # Delete rows that contain ';' in any column
            df_filtered = df_filt[df_filt[col_name].isin(valid_values)]
            output_path = os.path.join(output_folder, os.path.basename(file_path))
            df_filtered.to_csv(output_path, index=False)
        else:
            print(f"Column '{col_name}' not found in {file_path}. Skipping file.")

folder_path =  r'D:\smarrakchi\Gridnet_UCAN_data\annotations_v2_mod'
col_name = 'AARs'
valid_values = AARs 
output_folder = r'D:\smarrakchi\Gridnet_UCAN_data\annotations_v2_final'

filter_csv_files(folder_path, col_name, valid_values, output_folder)

###
# This is to remove the files that are in the images/tissue_pos folders but not in the anno folder
def list_files(folder):
    return [file for file in os.listdir(folder) if os.path.isfile(os.path.join(folder, file))]

anno_files = list_files(r'C:\Users\smarrakchi\Desktop\Gridnet_UCAN_data\annotations')
img_files = list_files(r'D:\smarrakchi\pseudo_visium\fullres_rois')

def list_dirs(folder):
    return [name for name in os.listdir(folder) if os.path.isdir(os.path.join(folder, name))]

tissue_pos_files = list_dirs(r'D:\smarrakchi\pseudo_visium\pseudo_spaceranger')

def get_file_names_without_extension(files):
    return [os.path.splitext(file)[0] for file in files]

anno_base_names = set(get_file_names_without_extension(anno_files))
filt_tissue_pos = [file for file in tissue_pos_files if file in anno_base_names]
filt_img_files = [file for file in img_files if os.path.splitext(file)[0] in anno_base_names]

source_folder = r'D:\smarrakchi\pseudo_visium\pseudo_spaceranger'
destination_folder = r'D:\smarrakchi\Gridnet_UCAN_data\tissue_pos_lists'
subfolders_to_keep = filt_tissue_pos

if not os.path.exists(destination_folder):
    os.makedirs(destination_folder)

for subfolder in os.listdir(source_folder):
    subfolder_path = os.path.join(source_folder, subfolder)
    if os.path.isdir(subfolder_path) and subfolder in subfolders_to_keep:
        shutil.copytree(subfolder_path, os.path.join(destination_folder, subfolder),dirs_exist_ok=True)
import os

folder_path =  r'D:\smarrakchi\Gridnet_UCAN_data\fullres_images'
names_to_keep = anno_base_names

for filename in os.listdir(folder_path):
    if filename.lower().endswith('.jpg'):
        base_name = os.path.splitext(filename)[0]
        if base_name not in names_to_keep:
            file_path = os.path.join(folder_path, filename)
            os.remove(file_path)
            print(f"Deleted: {file_path}")
