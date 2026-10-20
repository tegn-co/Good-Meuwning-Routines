# Bundle the Graphene 1.0 typelib and its dependencies (in case pyinstaller-hooks-contrib has no hook for it)
from PyInstaller.utils.hooks.gi import GiModuleInfo

module_info = GiModuleInfo("Graphene 1.0", "")
if module_info.available:
    binaries, datas, hiddenimports = module_info.collect_typelib_data()
