import {
  createElement,
  useLayoutEffect,
  useRef,
  useState,
  type SVGProps,
} from 'react';
import {
  ApiBlueprint,
  createFrontendModule,
  type IconComponent,
} from '@backstage/frontend-plugin-api';
import {
  catalogApiRef,
  defaultEntityPresentation,
  entityPresentationApiRef,
} from '@backstage/plugin-catalog-react';
import { DefaultEntityPresentationApi } from '@backstage/plugin-catalog';
import type { IconType } from 'react-icons';
import { LuBot, LuCpu } from 'react-icons/lu';
import { MdPsychology } from 'react-icons/md';
import { PiList, PiQueue } from 'react-icons/pi';
import { SiKubernetes } from 'react-icons/si';
import { TbBucket, TbDatabase, TbMicrophone, TbWorldWww } from 'react-icons/tb';

type GraphIconProps = SVGProps<SVGSVGElement> & { icon: IconType };

// The catalog graph colours a node icon by setting CSS `fill` on it (via
// className), which suits MUI's filled icons but breaks outline icons
// (Tabler, Lucide): their inside gets filled and the stroke keeps the page text
// colour. Here the icon sits in an outer <svg> that receives the graph's props;
// the fill the graph computed for it becomes the inner icon's `color`, which
// both outline (stroke) and filled react-icons draw with.
const GraphIcon = ({ icon: Icon, style, ...props }: GraphIconProps) => {
  const ref = useRef<SVGSVGElement>(null);
  const [color, setColor] = useState<string>();
  useLayoutEffect(() => {
    if (ref.current) {
      setColor(getComputedStyle(ref.current).fill);
    }
  }, [props.className]);
  return createElement(
    'svg',
    { ref, ...props, style: { ...style, overflow: 'visible' } },
    createElement(Icon, { size: '100%', style: { color } }),
  );
};

// react-icons take `size`, Backstage passes MUI's `fontSize`. In lists and
// cards the icon renders at 1em, following the surrounding font size like MUI
// icons do; the catalog graph passes className/x/y/width/height instead.
const fromReactIcons = (Icon: IconType): IconComponent => {
  const Wrapped = ({
    fontSize: _fontSize,
    ...props
  }: SVGProps<SVGSVGElement> & { fontSize?: string }) =>
    props.className
      ? createElement(GraphIcon, { icon: Icon, ...props })
      : createElement(Icon, { size: '1em' });
  Wrapped.displayName = `ReactIcon(${Icon.name})`;
  return Wrapped;
};

// Icon per `wasp.io/icon` annotation; wins over the type mapping below.
const ICON_ANNOTATION = 'wasp.io/icon';
const annotationIcons: Record<string, IconComponent> = {
  bot: fromReactIcons(LuBot),
};

// Icon per `<kind>:<spec.type>`; anything else falls back to the kind icon.
const typeIcons: Record<string, IconComponent> = {
  'resource:queue': fromReactIcons(PiQueue),
  'resource:topic': fromReactIcons(PiList),
  'resource:database': fromReactIcons(TbDatabase),
  'resource:object-storage': fromReactIcons(TbBucket),
  'resource:llm-provider': fromReactIcons(MdPsychology),
  'resource:speech-to-text': fromReactIcons(TbMicrophone),
  'resource:kubernetes-cluster': fromReactIcons(SiKubernetes),
  'component:service': fromReactIcons(LuCpu),
  'component:website': fromReactIcons(TbWorldWww),
};

// Same ID as the catalog plugin's default (api:catalog/entity-presentation),
// so it replaces it.
const entityPresentationApi = ApiBlueprint.make({
  name: 'entity-presentation',
  params: defineParams =>
    defineParams({
      api: entityPresentationApiRef,
      deps: { catalogApi: catalogApiRef },
      factory: ({ catalogApi }) =>
        DefaultEntityPresentationApi.create({
          catalogApi,
          renderer: {
            async: true,
            render: ({ entityRef, entity, context }) => {
              const presentation = defaultEntityPresentation(
                entity || entityRef,
                context,
              );
              const annotation =
                entity?.metadata.annotations?.[ICON_ANNOTATION];
              const type = entity?.spec?.type;
              const Icon =
                (annotation && annotationIcons[annotation]) ||
                (entity && typeof type === 'string'
                  ? typeIcons[`${entity.kind.toLowerCase()}:${type}`]
                  : undefined);
              return {
                snapshot: Icon ? { ...presentation, Icon } : presentation,
                loadEntity: true,
              };
            },
          },
        }),
    }),
});

export const entityPresentationModule = createFrontendModule({
  pluginId: 'catalog',
  extensions: [entityPresentationApi],
});
