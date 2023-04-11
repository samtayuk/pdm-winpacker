import shutil
import zipfile
import re
import fnmatch
import os
from pathlib import Path
from tempfile import mkdtemp



def normalize_path(path):
    """Normalize paths to contain "/" only"""
    return os.path.normpath(path).replace('\\', '/')

def is_excluded(path, exclude_regexen):
    """Return True if path matches an exclude pattern"""
    path = normalize_path(path)
    for re_pattern in exclude_regexen:
        if re_pattern.match(path):
            return True
    return False

def merge_dir_to(src, dst):
    """Merge all files from one directory into another.

    Subdirectories will be merged recursively. If filenames are the same, those
    from src will overwrite those in dst. If a regular file clashes with a
    directory, an error will occur.
    """
    for p in src.iterdir():
        if p.is_dir():
            dst_p = dst / p.name
            if dst_p.is_dir():
                merge_dir_to(p, dst_p)
            elif dst_p.is_file():
                raise RuntimeError('Directory {} clashes with file {}'.format(p, dst_p))
            else:
                shutil.copytree(str(p), str(dst_p))
        else:
            # Copy regular file
            dst_p = dst / p.name
            if dst_p.is_dir():
                raise RuntimeError('File {} clashes with directory {}'.format(p, dst_p))
            shutil.copy2(str(p), str(dst_p))

def make_exclude_regexen(exclude_patterns):
    """Translate exclude glob patterns to regex pattern objects.

    Handles matching files under a named directory.
    """
    re_pats = set()
    for pattern in exclude_patterns:
        re_pats.add(fnmatch.translate(pattern))
        if not pattern.endswith('*'):
            # Also use the pattern as a directory name and match anything
            # under that directory.
            suffix = '*' if pattern.endswith('/') else '/*'
            re_pats.add(fnmatch.translate(pattern + suffix))

    return [re.compile(p) for p in sorted(re_pats)]

def extract_wheel(whl_file, target_dir, exclude=None):
    """Extract importable modules from a wheel to the target directory
    """
    # Extract to temporary directory
    td = Path(mkdtemp())
    with zipfile.ZipFile(str(whl_file), mode='r') as zf:
        if exclude:
            exclude_regexen = make_exclude_regexen(exclude)
            for zpath in zf.namelist():
                if is_excluded('pkgs/' + zpath, exclude_regexen):
                    continue  # Skip excluded paths
                zf.extract(zpath, path=str(td))
        else:
            zf.extractall(str(td))

    # Move extra lib files out of the .data subdirectory
    for p in td.iterdir():
        if p.suffix == '.data':
            if (p / 'purelib').is_dir():
                merge_dir_to(p / 'purelib', td)
            if (p / 'platlib').is_dir():
                merge_dir_to(p / 'platlib', td)

            # HACK: Some wheels from Christoph Gohlke's page have extra package
            # files added in data/Lib/site-packages. This is a trick that relies
            # on the default installation layout. It doesn't look like it will
            # change, so in the best tradition of packaging, we'll work around
            # the workaround.
            # https://github.com/takluyver/pynsist/issues/171
            # This is especially ugly because we do a case-insensitive match,
            # regardless of the filesystem.
            if (p / 'data').is_dir():
                for sd in (p / 'data').iterdir():
                    if sd.name.lower() == 'lib' and sd.is_dir():
                        for sd2 in sd.iterdir():
                            if sd2.name.lower() == 'site-packages' and sd2.is_dir():
                                merge_dir_to(sd2, td)

    # Copy to target directory
    target = Path(target_dir)
    copied_something = False
    for p in td.iterdir():
        if p.suffix not in {'.data'}:
            if p.is_dir():
                # If the dst directory already exists, this will combine them.
                # shutil.copytree will not combine them.
                try:
                    target.joinpath(p.name).mkdir()
                except OSError:
                    if not target.joinpath(p.name).is_dir():
                        raise
                merge_dir_to(p, target / p.name)
            else:
                shutil.copy2(str(p), str(target))
            copied_something = True

    if not copied_something:
        raise RuntimeError("Did not find any files to extract from wheel {}".format(whl_file))

    # Clean up temporary directory
    shutil.rmtree(str(td))