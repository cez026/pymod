# Copyright (C) 2014-2016 Giacomo Janson, Chengxin Zhang

import os
import sys
import urllib
import gzip

import pymol
from pymol import cmd

import pymod_lib.pymod_vars as pmdt
import pymod_lib.pymod_structure as pmstr
# import pymod_lib.pymod_os_specific as pmos
import pymod_lib.pymod_sequence_manipulation as pmsm
import pymod_lib.pymod_gui as pmgi

from pymod_lib.pymod_protocols.base_protocols import PyMod_protocol


###################################################################################################
# Fetch PDB files.                                                                                #
###################################################################################################

class Fetch_structure_file(PyMod_protocol):
    """
    Class for downloading a PDB file from the sequences retrived from BLAST.
    """

    def __init__(self, pymod, output_directory=None, mode=None, structures_to_fetch=None, import_mode=None):
        PyMod_protocol.__init__(self, pymod, output_directory)
        self.mode = mode
        self.structures_to_fetch = structures_to_fetch
        self.import_mode = import_mode


    def initialize_from_gui(self, mode, structures_to_fetch):
        # Builds a list of structures to be fetched.
        self.structures_to_fetch = []
        if mode == "single":
            self.structures_to_fetch.append(structures_to_fetch)
        elif mode == "selection":
            self.structures_to_fetch.extend(self.pymod.get_selected_sequences())


    def launch_from_gui(self):
        """
        Let the user choose the way in which to retrieve the structures.
        """
        self.fetch_pdb_dialog = pmgi.structural_databases_components.Fetch_pdb_dialog(self.pymod.main_window, self)


    def fetch_pdb_files_state(self, dialog_choice):
        """
        Gets the import mode from the GUI and then fetch the files.
        """
        self.import_mode = self.fetch_pdb_dialog.import_mode_choices.get(dialog_choice)
        self.fetch_pdb_dialog.withdraw()
        # Interrupt the process if users close the dialog window.
        if not self.import_mode:
            return None
        self.fetch_pdb_files()


    def fetch_pdb_files(self):
        """
        Actually fetch the PDB files.
        """
        for element in self.structures_to_fetch:
            self._fetch_single_element(element)
        self.pymod.main_window.gridder(update_elements=True, update_clusters=True)


    def _get_pdb_code_from_header(self, pymod_element):
        element_header = pymod_element.my_header
        if element_header.split("|")[2] == "pdb":
            pdb_code = element_header.split("|")[3]
            if element_header.split("|")[4] != "":
                pdb_chain = element_header.split("|")[4][0]
            else:
                pdb_chain = None
                # import_mode = "multiple-chains"
        elif element_header.split("|")[4] == "pdb":
            pdb_code=element_header.split("|")[5]
            if element_header.split("|")[6][0] != "":
                pdb_chain = element_header.split("|")[6][0]
            else:
                pdb_chain = None
                # import_mode = "multiple-chains"
        return str(pdb_code), str(pdb_chain) # Unicode strings are not recognized by MODELLER.


    def _fetch_structure_file(self, pdb_code, output_dir, new_name=None):
        return fetch_structure_file(pdb_code, output_dir, new_name=new_name)


    def _fetch_single_element(self, old_element):
        pdb_code, pdb_chain_id = self._get_pdb_code_from_header(old_element)
        try:
            pdb_file_shortcut = self._fetch_structure_file(pdb_code, self.pymod.temp_directory_name)
        except:
            title = "Connection Error"
            message = "Can not access to the PDB database.\nPlease check your Internet access."
            self.pymod.show_error_message(title, message)
            return False

        #--------------------------------------------------------------------------------------
        # Load in PyMod only the chain corresponding to the hit sequence and adjust its legth -
        # to the region identified by BLAST.                                                  -
        #--------------------------------------------------------------------------------------
        if self.import_mode == "single-chain":
            a = Associate_structure(self.pymod, pdb_file_shortcut, pdb_chain_id, old_element)
            a.associate()

        #--------------------------------------------------------------------------------------
        # Load each chain found in the PDB file where the 3D structure of the hit sequence is -
        # present. This is actually like opening a new PDB file with the                      -
        # 'open_structure_file()' method, except that in this case, the chains not            -
        # corresponging to the hit sequence are colored in gray.                              -
        #--------------------------------------------------------------------------------------
        elif self.import_mode == "multiple-chains":
            # Builds a 'Parsed_pdb_file' object.
            p = pmstr.Parsed_pdb_file(self.pymod, os.path.abspath(pdb_file_shortcut), output_directory=self.pymod.structures_directory)
            # Builds 'Pymod_elements' objects for each chain present in the PDB file.
            for new_element in p.get_pymod_elements():
                if new_element.get_chain_id() != pdb_chain_id:
                    self.pymod.add_element_to_pymod(new_element, load_in_pymol=True, color="gray")
                else:
                    # Deletes the original hit sequence retrieved by BLAST and replaces it with
                    # a new element with an associated structure loaded in PyMOL.
                    old_element.delete()
                    self.pymod.add_element_to_pymod(new_element, load_in_pymol=True)


class Structure_file_fetcher:

    def __init__(self, pdb_code, output_dir, new_name = None):
        self.pdb_code = pdb_code
        self.output_dir = output_dir
        # Form the pdb output name
        if new_name:
            self.output_name = '%s.pdb' % new_name
        else:
            self.output_name = '%s.pdb' % pdb_code

    def fetch(self):
        # Retrieve the PDB file from the internet.
        temp_gzipped_file_name = urllib.urlretrieve("http://www.rcsb.org/pdb/files/%s.pdb.gz" % self.pdb_code)[0]
        open_gzipped_file = gzip.open(temp_gzipped_file_name) # Uncompress the file while reading
        output_path = os.path.join(self.output_dir, self.output_name)
        saved_file = open(output_path, 'w')
        saved_file.write(open_gzipped_file.read()) # Write pdb file
        open_gzipped_file.close()
        saved_file.close()
        return output_path

def fetch_structure_file(pdb_code, output_dir, new_name = None):
    sf = Structure_file_fetcher(pdb_code, output_dir, new_name=new_name)
    return sf.fetch()


###################################################################################################
# Associate structures to PyMod elements.                                                         #
###################################################################################################

class Associate_structure(PyMod_protocol):
    """
    Once 'build_structure_objects()' has been used, this will edit the 'PyMod_element' and
    'Structure' objects corresponding to the 'chain_id' according to the sequence provided in
    the 'adjust_to_sequence' argument.
    Usually this is used when fetching a PDB file corresponding to some hit from a BLAST search,
    because hits in HSPs may have a shorter sequence with respect to the full PDB chain.
    This method can be called to crop the full 3D chain according to the hit sequence in the
    HSP (provided in the 'adjust_to_sequence' argument).
    """

    temp_full_name = "pymod_full_temp"
    temp_fragment_name = "pymod_fragment_temp"

    def __init__(self, pymod, pdb_file_path, chain_id, pymod_element):

        PyMod_protocol.__init__(self, pymod)

        self.original_pdb_file_path = pdb_file_path
        self.target_element = pymod_element
        self.chain_id = chain_id
        # Directory in which to save the temporary files.
        self.temp_directory = self.pymod.temp_directory_name
        # Directory in which to save the final output files.
        self.output_directory = self.pymod.structures_directory

        # Parses the source structure file.
        p = pmstr.Parsed_pdb_file(self.pymod, pdb_file_path, copy_original_file=False, save_chains_files=False)
        self.structure_chain_element = p.get_pymod_element_by_chain(self.chain_id)

        # Check if the the target sequence and the sequence of the structure to associate match by
        # aligning the two sequences using dynamic programming.
        self.ali = pmsm.global_pairwise_alignment(self.target_element.my_sequence.replace("-",""),
                                                  self.structure_chain_element.my_sequence.replace("-",""),
                                                  toss_modres=True)
        # If the sequences do not match, interrupt the process.
        if self.ali["id"] < 99.9: # TODO: use a 'PyMod_alignment' class.
            raise PyModAssociateStructureError("The target sequence does not match with the sequence of the structure to associate (id=%s)." % self.ali["id"])


    def associate(self):
        """
        Actually associates the structure.
        """

        #-------------------------------------------------------------------------------------
        # Gets information about matching and missing residues in the two aligned sequences. -
        #-------------------------------------------------------------------------------------
        pc = 0 # Alignment position counter.
        hc = 0 # Target residue counter.
        tc = 0 # PDB structure residue counter.
        matching_positions = [] # list of matching positions.
        missing_positions = [] # list of missing residues in the pdb structure with respect to the target sequence.
        for hr, tr in zip(self.ali["seq1"], self.ali["seq2"]):
            if hr != "-" and tr != "-" and hr == tr:
                matching_positions.append({"pc":pc,"hc":hc,"tc":tc})
            if tr == "-" and hr != "-":
                missing_positions.append({"pc":pc,"hc":hc,"tc":tc})
            if hr != "-":
                hc += 1
            if tr != "-":
                tc += 1
            pc += 1
        # Gets the starting and ending positions (using the PDB numeration) that will be used to
        # crop the 3D structure.
        start_position = self.structure_chain_element.get_residue_by_index(matching_positions[0]["tc"]).db_index
        end_position = self.structure_chain_element.get_residue_by_index(matching_positions[-1]["tc"]).db_index

        #------------------------------------------------
        # Use PyMOL to build the new cropped structure. -
        #------------------------------------------------
        # First loads the full PDB structure of the chain in PyMOL.
        cmd.load(self.original_pdb_file_path, self.temp_full_name)
        # Select amminoacidic residues ranging from the starting and ending positions which define
        # the fragment to "excise".
        cmd.select(self.temp_fragment_name, "resi %s-%s and chain %s and object %s and not hetatm" % (start_position, end_position, self.chain_id, self.temp_full_name))
        # Join the selections and save a file PDB file of the cropped fragment.
        pdb_basename = "%s_cropped.pdb" % self.structure_chain_element.get_structure_file_root()
        cropped_structure_file_shortcut = os.path.join(self.temp_directory, pdb_basename)
        cmd.save(cropped_structure_file_shortcut, self.temp_fragment_name)
        # Clean up the selections.
        cmd.delete(self.temp_full_name)
        cmd.delete(self.temp_fragment_name)

        #----------------------------------------------------------------------------------
        # Builds a 'Parsed_pdb_file' object for the PDB file of the structure just saved. -
        #----------------------------------------------------------------------------------
        p = pmstr.Parsed_pdb_file(self.pymod, os.path.abspath(cropped_structure_file_shortcut), output_directory=self.output_directory)
        new_element_with_structure = p.get_pymod_element_by_chain(self.chain_id)
        adjust_to_sequence = self.target_element.my_sequence
        self.pymod.replace_element(self.target_element, new_element_with_structure)

        #--------------------------------------------------------------------------------------
        # Updates the sequence of the fragment to keep it in frame with the original sequence -
        # provided in 'adjust_to_sequence' by including the target sequence indels.           -
        #--------------------------------------------------------------------------------------
        list_of_missing_positions = [p["hc"] for p in missing_positions]
        new_sequence = []
        adc = 0
        for i, p in enumerate(list(adjust_to_sequence)):
            if adc in list_of_missing_positions:
                new_sequence.append("-")
            else:
                # Right now modified residues are not included in the cropped structures,
                # this prevents them from being included in the chain sequence.
                if p != "X":
                    new_sequence.append(p)
                else:
                    new_sequence.append("-")
            if p != "-":
                adc += 1
        new_sequence = "".join(new_sequence)
        new_element_with_structure.set_sequence(new_sequence)


    # def associate_structure_from_popup_menu(self, target_element):
    #     """
    #     Launched when users press the 'Associate 3D Structure' from the leeft popup menu.
    #     """
    #     pass
    #     # # This will be set to 'True' once the users select a valid PDB file and press the 'SUBMIT'
    #     # # button.
    #     # self.select_associate_chain = False
    #     # # This will contain the 'Parsed_pdb_file' object of the structure to associate.
    #     # self.associate_pdb_file = None
    #     # # The 'PyMod_element' object of the target seequence (the sequence to be associated with a
    #     # # structure).
    #     # self.associate_target_element = target_element
    #     #
    #     # # Builds a new window.
    #     # self.associate_structure_window = pmgi.shared_components.PyMod_tool_window(self.main_window,
    #     #     title = "Associate Structure",
    #     #     upper_frame_title = "Associate 3D Structure Options",
    #     #     submit_command = self.associate_structure_state)
    #     #
    #     # # An entryfield to select the structure file.
    #     # self.structure_file_enf = pmgi.shared_components.PyMod_path_entryfield(self.associate_structure_window.midframe,
    #     #     label_text = "Select Structure File",
    #     #     label_style = pmgi.shared_components.label_style_1,
    #     #     path_type = "file",
    #     #     file_types = pmdt.all_structure_file_types_atl,
    #     #     askpath_title = "Select Structure File")
    #     # self.structure_file_enf.pack(**pmgi.shared_components.pack_options_1)
    #     # self.associate_structure_window.add_widget_to_align(self.structure_file_enf)
    #     # self.associate_structure_window.add_widget_to_validate(self.structure_file_enf)
    #     #
    #     # self.associate_structure_window.align_widgets(15)
    #
    #
    # # TODO!!
    # def associate_structure_state(self):
    #     pass
    #     # # Checks if a correct structure file has been provided as input.
    #     # if not self.select_associate_chain:
    #     #     if not self.check_general_input(self.associate_structure_window):
    #     #         return False
    #     #     pdb_file_path = self.structure_file_enf.getvalue()
    #     #
    #     #     if not self.is_pdb(pdb_file_path, show_error=False):
    #     #         title = "File Type Error"
    #     #         message = "Please select a valid PDB file."
    #     #         self.show_error_message(title,message, parent_window=self.associate_structure_window)
    #     #         return False
    #     #     # Removes the entryfield to select the structure file.
    #     #     self.structure_file_enf.pack_forget()
    #     #
    #     #     # Parses the structure file.
    #     #     self.associate_pdb_file = Parsed_pdb_file(pdb_file_path)
    #     #     self.associate_pdb_file.copy_to_structures_directory()
    #     #     self.associate_pdb_file.parse_pdb_file()
    #     #     # Gets its chains.
    #     #     available_chains = self.associate_pdb_file.get_chains_ids()
    #     #
    #     #     # Displays a combobox to select the chain id of corresponind to the structure to be
    #     #     # associated with the target sequence.
    #     #     self.chain_selection_cbx = pmgi.shared_components.PyMod_combobox(self.associate_structure_window.midframe,
    #     #         label_text = 'Select Chain to Associate',
    #     #         label_style = pmgi.shared_components.label_style_1,
    #     #         scrolledlist_items=available_chains)
    #     #     self.chain_selection_cbx.pack(**pmgi.shared_components.pack_options_1)
    #     #     self.chain_selection_cbx.selectitem(0)
    #     #     self.associate_structure_window.add_widget_to_align(self.chain_selection_cbx)
    #     #     self.associate_structure_window.align_widgets(15)
    #     #
    #     #     self.select_associate_chain = True
    #     #
    #     # # If a valid structure file has been provided, this will try to associate the structure of
    #     # # the chain specified in the combobox to the target element.
    #     # elif self.select_associate_chain:
    #     #     if not self.associate_structure(self.associate_pdb_file, self.chain_selection_cbx.get(), self.associate_target_element):
    #     #         self.show_associate_structure_error(parent_window = self.associate_structure_window)
    #     #         return False
    #     #     self.associate_structure_window.destroy()
    #     #     self.main_window.gridder()
    #
    #
    # def show_associate_structure_error(self, parent_window = None):
    #     title = "Associate Structure Failure"
    #     message = "The amminoacid sequences of the target chain and the chain in the PDB structure do not match."
    #     self.show_error_message(title, message)
    #
    # # TODO!!
    # def associate_structure(self, parsed_pdb_file, chain_id, pymod_element):
    #     """
    #     Gets a 'Parsed_pdb_file' object and a 'PyMod_element' object as arguments, and associates
    #     the structure with chain id specified in 'chain_id' to the PyMod element.
    #     """
    #     pass
    #     # # Builds 'Pymod_elements' objects for each chain present in the PDB file.
    #     # parsed_pdb_file.build_structure_objects(add_to_pymod_pdb_list = False)
    #     # # Crops the structure.
    #     # sequences_match = parsed_pdb_file.crop_structure_chain(chain_id, adjust_to_sequence = pymod_element.my_sequence)
    #     # if not sequences_match:
    #     #     return False
    #     # # Build a 'PyMod_element' object representing the cropped chain and transfer its
    #     # # data to the element if the hit sequence.
    #     # cropped_element = parsed_pdb_file.get_chain_pymod_element(chain_id)
    #     # pymod_element.update_element(new_sequence=cropped_element.my_sequence, new_header=cropped_element.my_header, new_structure=cropped_element.structure)
    #     # pymod_element.my_color = self.color_struct()
    #     # self.load_element_in_pymol(pymod_element)
    #     # parsed_pdb_file.add_to_pdb_list()
    #     # return True


###################################################################################################
# EXCEPTIONS.                                                                                     #
###################################################################################################

class PyModAssociateStructureError(Exception):
    """
    Used a mismatch is encountered when trying to associate a structure to a PyMod element.
    """
    pass
