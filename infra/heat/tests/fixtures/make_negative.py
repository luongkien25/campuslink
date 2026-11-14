"""Sinh ban sao HOT gay loi DB chi tren app A hoac B; khong chay cloud."""
import argparse
from pathlib import Path
import shutil
import yaml

HEAT = Path(__file__).resolve().parents[2]


class PlainDumper(yaml.SafeDumper):
    def ignore_aliases(self, data):
        return True


def walk(value):
    if isinstance(value, dict):
        if 'get_file' in value:
            yield value['get_file']
        for child in value.values():
            yield from walk(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk(child)


def build(destination, side):
    if side not in ('a','b'):
        raise ValueError('side must be a or b')
    destination = Path(destination)
    destination.mkdir(mode=0o700)
    root = yaml.safe_load((HEAT/'root.yaml').read_text())
    unit = yaml.safe_load((HEAT/'app-unit.yaml').read_text())
    env = (HEAT/'../../app/shlink.env.example').resolve().read_text()
    fault = env.replace('\nDB_HOST=10.20.0.10\n', '\nDB_HOST=127.0.0.1\n')
    if fault == env:
        raise ValueError('DB_HOST contract changed')
    root['resources']['app_a']['properties']['app_env'] = fault if side=='a' else env
    root['resources']['asg_b']['properties']['resource']['properties']['app_env'] = fault if side=='b' else env
    for name, template in [('root.yaml',root),('app-unit.yaml',unit)]:
        for relative in walk(template):
            target = destination/relative
            target.resolve().relative_to(destination.resolve())
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(HEAT/relative, target)
        (destination/name).write_text(yaml.dump(template,Dumper=PlainDumper,sort_keys=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Create standalone negative HOT copy; no cloud changes')
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--fault',choices=('a','b'),required=True)
    args = parser.parse_args()
    build(args.out,args.fault)
