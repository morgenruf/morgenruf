import path from 'node:path';
import { fileURLToPath, URL } from 'node:url';

const sourceRoot = fileURLToPath(new URL('../src', import.meta.url));

function location(filename) {
  const relative = path.relative(sourceRoot, filename);

  if (relative.startsWith(`..${path.sep}`) || path.isAbsolute(relative))
    return null;

  return relative.split(path.sep);
}

export default {
  meta: {
    type: 'problem',
    docs: {
      description:
        'Keep feature internals private and shared code independent of application and feature layers.',
    },
    schema: [],
    messages: {
      boundary:
        '{{from}} cannot import {{to}}. Share reusable code through src/common; keep feature internals within their module.',
    },
  },
  create(context) {
    const filename = context.filename ?? context.getFilename();
    const importer = location(filename);

    if (!importer || !['modules', 'common'].includes(importer[0])) return {};

    function check(node) {
      const source = node.source;

      if (!source || typeof source.value !== 'string') return;

      const specifier = source.value;
      let target;

      if (specifier.startsWith('@/'))
        target = path.join(sourceRoot, specifier.slice(2));
      else if (specifier.startsWith('.'))
        target = path.resolve(path.dirname(filename), specifier);
      else return;

      const imported = location(target);
      const ownFeature = importer[0] === 'modules' ? importer[1] : null;
      const crossesFeature =
        imported?.[0] === 'modules' && imported[1] !== ownFeature;
      const importsApp =
        imported?.[0] === 'app' ||
        imported?.[0] === 'routes' ||
        /^router(?:\.[cm]?[jt]sx?)?$/.test(imported?.[0] ?? '') ||
        imported?.[0]?.startsWith('routeTree.gen');

      if (crossesFeature || importsApp || !imported) {
        context.report({
          node: source,
          messageId: 'boundary',
          data: {
            from: ownFeature ? `Feature ${ownFeature}` : 'Shared code',
            to: imported ? `src/${imported.slice(0, 2).join('/')}` : specifier,
          },
        });
      }
    }

    return {
      ImportDeclaration: check,
      ExportNamedDeclaration: check,
      ExportAllDeclaration: check,
      ImportExpression: check,
    };
  },
};
