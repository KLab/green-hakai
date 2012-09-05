import virtualenv

extra = """
import sys
def after_install(options, home_dir):
    if sys.platform == 'win32':
        bin = 'Scripts'
    else:
        bin = 'bin'
    pip = os.path.join(home_dir, bin, 'pip')
    subprocess.call([pip, 'install', '-r', 'requirements.txt'])
"""

with open('ghakai-bootstrap.py', 'w') as f:
    f.write(virtualenv.create_bootstrap_script(extra))
