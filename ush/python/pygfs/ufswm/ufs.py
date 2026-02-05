import os
import shutil
from wxflow import Logger, AttrDict, Template, TemplateConstants, Executable

logger = Logger(level=os.environ.get("LOGGING_LEVEL", "INFO"))


class UFS:
    def __init__(self, config):
        self.config = AttrDict(config)

    def parse_ufs_templates(self, tmpl_dict: dict, output_dir: str):
        """
        Parses UFS control files from templates
        """
        for filename, tmpl_str in tmpl_dict.items():
            logger.info(f"Generating {filename} from template")
            content = Template.substitute_string(
                tmpl_str,
                TemplateConstants.DOLLAR_CURLY_BRACE,
                self.config.get
            )
            with open(os.path.join(output_dir, filename), 'w') as f:
                f.write(content)

    def copy_fix_files(self, fix_files: list, target_dir: str):
        """
        Copies fix files to target directory
        """
        for src, dest in fix_files:
            logger.info(f"Copying {src} to {os.path.join(target_dir, dest)}")
            shutil.copy2(src, os.path.join(target_dir, dest))

    def run_ufs(self, working_dir: str, exec_path: str, ntasks: int):
        """
        Executes the UFS model
        """
        logger.info(f"Executing UFS model: {exec_path} with {ntasks} tasks")
        # In a real environment, we'd use a proper MPI launcher
        # For now, we simulate with wxflow.Executable
        cmd = f"mpirun -n {ntasks} {exec_path}"
        exe = Executable(cmd, cwd=working_dir)
        exe.execute()
        if exe.returncode != 0:
            raise RuntimeError(f"UFS failed with return code {exe.returncode}")
