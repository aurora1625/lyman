"""Defines a class for flexible functional mask generation."""
import os
import os.path as op
import shutil
from tempfile import mkdtemp
from subprocess import check_output
from IPython.parallel import Client
from IPython.parallel.error import TimeoutError

from . import main


class MaskFactory(object):
    """Class for the rapid and flexible creation of functional masks.

    This class can make appropriate calls to external (Freesurfer and
    FSL) command-line programs to take ROIs defined in a variety of
    sources and generate binary mask images in native EPI space.

    """
    def __init__(self, subject_list, experiment, roi_name,
                 orig_type, force_serial=False, debug=False):

        # Set up basic info
        self.subject_list = main.determine_subjects(subject_list)
        project = main.gather_project_info()
        self.experiment = experiment
        self.roi_name = roi_name
        self.orig_type = orig_type
        self.debug = debug
        if debug:
            print "Setting up for %d subjects" % len(subject_list)
            print "Experiment name:", experiment
            print "ROI name:", roi_name

        # Set up directories
        if project["default_exp"] is not None and experiment is None:
            experiment = project["default_exp"]
        self.experiment = experiment
        self.data_dir = project["data_dir"]
        self.anal_dir = project["analysis_dir"]

        # Set up temporary output
        self.temp_dir = mkdtemp()

        # Set the SUBJECTS_DIR variable for Freesurfer
        os.environ["SUBJECTS_DIR"] = self.data_dir

        # Set up parallel execution
        self.parallel = False
        if force_serial:
            self.map = map
        else:
            try:
                rc = Client()
                self.dv = rc[:]
                self.map = self.dv.map_async
                # Push SUBJECTS_DIR to engines
                self.dv.execute("import os")
                self.dv["data_dir"] = self.data_dir
                self.dv.execute("os.environ['SUBJECTS_DIR'] = data_dir")
                self.parallel = True

            except (TimeoutError, IOError):
                self.map = map
        if debug:
            print "Set to run in %s" % (
                "parallel" if self.parallel else "serial")

        # Set up some persistent templates
        self.epi_template = op.join(self.anal_dir, self.experiment,
                                    "%(subj)s",
                                    "preproc/run_1/mean_func.nii.gz")
        self.reg_template = op.join(self.anal_dir, self.experiment,
                                    "%(subj)s",
                                    "preproc/run_1/func2anat_tkreg.dat")
        self.out_template = op.join(self.data_dir,
                                    "%(subj)s",
                                    "masks/%s.nii.gz" % self.roi_name)
        if debug:
            print "EPI template: %s" % self.epi_template
            print "Reg template: %s" % self.reg_template
            print "Output template: %s" % self.out_template

        # Ensure the output directory will exist
        for subj in self.subject_list:
            mask_dir = op.join(self.data_dir, subj, "masks")
            if not op.exists(mask_dir):
                os.mkdir(mask_dir)

    def __del__(self):

        if self.debug:
            print "Debug mode: not removing output directory:"
            print self.temp_dir
        else:
            shutil.rmtree(self.temp_dir)

    def from_common_label(self, label_template, hemis, proj_args,
                          save_native=False):
        """Reverse normalize possibly bilateral labels to native space."""
        native_label_temp = op.join(self.temp_dir,
                                    "%(hemi)s.%(subj)s_native_label.label")

        # Transform by subject and hemi
        warp_cmds = []
        for subj in self.subject_list:
            for hemi in hemis:
                args = dict(hemi=hemi, subj=subj)
                cmd = ["mri_label2label",
                       "--srcsubject", "fsaverage",
                       "--trgsubject", subj,
                       "--hemi", hemi,
                       "--srclabel", label_template % args,
                       "--trglabel", native_label_temp % args,
                       "--regmethod", "surface"]
                warp_cmds.append(cmd)

        # Execute the transformation
        self.execute(warp_cmds, native_label_temp)

        # Possibly copy the resulting native space label to
        # the subject's label directory
        if save_native:
            save_temp = op.join(self.data_dir, "%(subj)s", "label",
                                "%(hemi)s." + self.roi_name + ".label")
            for subj in self.subject_list:
                for hemi in hemis:
                    args = dict(subj=subj, hemi=hemi)
                    shutil.copyfile(native_label_temp % args, save_temp % args)

        # Carry on with the native label stage
        self.from_native_label(native_label_temp, hemis, proj_args)

    def from_native_label(self, label_template, hemis, proj_args):
        """Given possibly bilateral native labels, make epi masks."""
        indiv_mask_temp = op.join(self.temp_dir,
                                  "%(hemi)s.%(subj)s_mask.nii.gz")
        # Command list for this step
        proj_cmds = []
        for subj in self.subject_list:
            for hemi in hemis:
                args = dict(hemi=hemi, subj=subj)
                cmd = ["mri_label2vol",
                       "--label", label_template % args,
                       "--temp", self.epi_template % args,
                       "--reg", self.reg_template % args,
                       "--hemi", hemi,
                       "--subject", subj,
                       "--o", indiv_mask_temp % args,
                       "--proj"]
                cmd.extend(proj_args)
                proj_cmds.append(cmd)

        # Execute the projection from a surface label
        self.execute(proj_cmds, indiv_mask_temp)

        # Combine the bilateral masks into the final mask
        combine_cmds = []
        for subj in self.subject_list:
            cmd = ["mri_concat"]
            for hemi in hemis:
                args = dict(hemi=hemi, subj=subj)
                cmd.append(indiv_mask_temp % args)
            cmd.extend(["--max",
                        "--o", self.out_template % dict(subj=subj)])
            combine_cmds.append(cmd)

        # Execute the final step
        self.execute(combine_cmds, self.out_template)

    def from_hires_atlas(self, hires_atlas_template, region_ids):
        """Create epi space mask from index volume (e.g. aseg.mgz"""
        hires_mask_template = op.join(self.temp_dir,
                                      "%(subj)s_hires_mask.nii.gz")

        # First run mri_binarize
        bin_cmds = []
        for subj in self.subject_list:
            args = dict(subj=subj)
            cmd_list = ["mri_binarize",
                        "--i", hires_atlas_template % args,
                        "--o", hires_mask_template % args]
            for id in region_ids:
                cmd_list.extend(["--match", str(id)])
            bin_cmds.append(cmd_list)
        self.execute(bin_cmds, hires_mask_template)

        self.from_hires_mask(hires_mask_template)

    def from_hires_mask(self, hires_mask_template):
        """Create epi space mask from hires mask (binary) volume."""
        xfm_cmds = []
        for subj in self.subject_list:
            args = dict(subj=subj)
            xfm_cmds.append(
                      ["mri_vol2vol",
                       "--mov", self.epi_template % args,
                       "--targ", hires_mask_template % args,
                       "--inv",
                       "--o", self.out_template % args,
                       "--reg", self.reg_template % args,
                       "--no-save-reg",
                       "--nearest"])
        self.execute(xfm_cmds, self.out_template)

    def from_statistical_file(self, stat_file_temp, thresh):
        """Create a mask by binarizing an epi-space fixed effects zstat map."""
        bin_cmds = []
        for subj in self.subject_list:
            args = dict(subj=subj)
            cmd = ["fslmaths",
                   stat_file_temp % args,
                   "-thr", thresh,
                   "-bin",
                   self.out_template % args]
            bin_cmds.append(cmd)

        self.execute(bin_cmds, self.out_template)

    def write_png(self):
        """Write a mosiac png showing the masked voxels."""
        overlay_temp = op.join(self.temp_dir, "%(subj)s_overlay.nii.gz")
        slices_temp = op.join(self.data_dir, "%(subj)s/masks",
                              self.roi_name + ".png")

        overlay_cmds = []
        for subj in self.subject_list:
            args = dict(subj=subj)
            overlay_cmds.append(
                          ["overlay", "1", "0",
                           self.epi_template % args, "-a",
                           self.out_template % args, "0.6", "2",
                           overlay_temp % args])
        self.execute(overlay_cmds, overlay_temp)

        slicer_cmds = []
        for subj in self.subject_list:
            args = dict(subj=subj)
            slicer_cmds.append(
                          ["slicer",
                           overlay_temp % args,
                           "-A", "750",
                           slices_temp % args])
        self.execute(slicer_cmds, slices_temp)

    def execute(self, cmd_list, out_temp):
        """Exceute a list of commands and verify output file existence."""
        res = self.map(check_output, cmd_list)
        if self.parallel:
            if self.debug:
                res.wait_interactive()
            else:
                res.wait()
        if self.parallel:
            if not res.successful():
                raise RuntimeError(res.pyerr)
        else:
            self.check_exists(out_temp)

    def check_exists(self, fpath_temp):
        """Ensure that output files exist on disk."""
        fail_list = []
        for hemi in ["lh", "rh"]:
            for subj in self.subject_list:
                args = dict(hemi=hemi, subj=subj)
                f_want = fpath_temp % args
                if not op.exists(f_want):
                    fail_list.append(f_want)
        if fail_list:
            print "Failed to write files:"
            print "\n".join(fail_list)
            raise RuntimeError
