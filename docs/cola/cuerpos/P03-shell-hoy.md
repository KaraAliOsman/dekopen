# P03 — Shell, navegación por flujo de trabajo e “Inicio: Hoy” por rol

**Depende de:** P01. Conviene que P02 ya esté mergeado para que se vean códigos humanos.

## Objetivo
Que al entrar cada rol vea **qué tiene que hacer hoy y por qué**, y que la navegación siga el flujo real de una fábrica de ventanas (vender → diseñar → producir → entregar), no una lista de módulos técnicos.

## Situación actual
- El shell vive en `frontend/src/app/`: `AppShell.tsx`, `railIcons.tsx`, `ShellCrumbs.tsx`, `AttentionBell.tsx`, `attention.ts`, `OrgSwitcher.tsx`, `ProjectSwitcher.tsx` y `DashboardPage.tsx`. La paleta de comandos está en `frontend/src/features/commands/`.
- (auditoría) La navegación agrupa “Trabajo: Panel/Proyectos/Clientes/Ventas · Operación: Catálogo/Compras/Producción/Asistente/Trabajos · Cuenta: Administración”. El “Panel del taller” es casi todo tarjetas de contadores vacías (“Necesita atención”, “Despachadas 30 d: 0”, “Instaladas 30 d: 0”) y proyectos recientes con hash. `/inventory` redirige a `/purchasing`.

## Diseño objetivo
1. **Barra lateral con etiquetas** (ícono + texto, colapsable a íconos con tooltip), agrupada por flujo:
   - **Inicio**
   - **Ventas:** Clientes, Proyectos, Cotizaciones (lista transversal con estado, vigencia y “vista por el cliente”) y Precios (solo roles con permiso).
   - **Ingeniería:** Catálogo técnico.
   - **Operación:** Compras, Inventario (stock y retazos, como ruta propia aunque al principio reutilice componentes), Producción, y Despacho e instalación solo si el backend ya tiene esos datos. **No crees secciones vacías.**
   - **Asistente:** Asistente y Trabajos.
   - **Ajustes**
   - Las entradas se ocultan según la capacidad del rol. El backend sigue siendo la autoridad: la UI solo refleja.
2. **Barra superior** con migas de pan que usan códigos humanos (“Proyectos › P-000012 Edificio Prat › Pos. 03 Living”), selector de organización y de proyecto, búsqueda global `Ctrl K` que encuentra clientes, proyectos, cotizaciones, OT, OC y retazos por código o nombre (reutiliza `backend/search`), campana de atención y ayuda de atajos con `?`.
3. **Inicio “Hoy”**: una cola de acciones por rol. Cada ítem es una frase en lenguaje de negocio + el código de la entidad + un CTA + el motivo, ordenada por urgencia.
   - **Estimador:** cotizaciones por vencer (≤ 3 días), propuestas vistas sin respuesta, cambios solicitados por clientes, aprobaciones de precio rechazadas o aprobadas y posiciones con bloqueos.
   - **Dueño:** aprobaciones de margen pendientes, cobros vencidos o saldos por cobrar, pipeline en $ por fase (con datos reales) y OTs comprometidas en riesgo.
   - **Jefe de producción:** OTs bloqueadas (faltante, QC, sin optimizar), próximas a despacho, cola por estación y remakes abiertos.
   - **Operario:** ir directo a su vista de estación (la diseña P12; mientras tanto, a la existente).
   - **Instalador:** despachos o instalaciones del día.
   - Contadores solo cuando son accionables y llevan a una lista filtrada. Si no hay nada, un solo estado vacío tranquilo (“Todo al día”), **sin tarjetas en cero**.
   - Si falta un endpoint para un ítem, créalo en el backend con RLS y tests. No calcules en el frontend agregados que deberían venir del backend.
4. **Responsivo:** menos de 1024 px → la barra lateral pasa a drawer; 390 px usable para estimador e instalador.

## Fuera de alcance
No rediseñes las páginas internas (proyecto, editor, producción, etc.). Mantén las URL existentes; si renombras, agrega redirecciones.

## Punto de vista y estándar de esta superficie
Aplica la constitución (`docs/design/CONSTITUCION.md`) completa; esto es lo específico de este encargo.
- **Persona y lo que debe sentir:** Cada rol al entrar por la mañana. Debe sentir: “sé qué hacer ahora y por qué”.
- **Anatomía:** Constitución §5.1 (shell) y §5.2 (Hoy). Navegación por flujo; paleta de comandos `Ctrl+K` conectada al registro de operaciones (el mismo que usa la IA).
- **Momento de firma (preservar o crear):** F8: el Orb vive en la barra superior y refleja trabajos reales; F3: las esperas usan el cargador de cota.
- **Idea que sube el techo (obligatoria, con el motor):** “Hoy” no es un dashboard: es una cola ordenada por consecuencia (lo que vence, lo que bloquea a otros, lo que pierde plata), donde cada fila trae su verbo y se resuelve sin navegar.
- **Slop a eliminar aquí:** Tarjetas de KPI con contadores en 0, saludo “¡Bienvenido de nuevo!”, gráficos decorativos, navegación por tablas de la base de datos, ilustraciones genéricas.
- **Preguntas del pase editorial:** Si quito cada widget, ¿alguien pierde una decisión? ¿Un dueño entiende en 5 segundos dónde está el problema de hoy?

## Criterios de aceptación
- Capturas del Inicio por cada rol del fixture (5 roles) en 1440 y 390 claro/oscuro, cada una con ítems reales del fixture.
- Test de la matriz rol → entradas de navegación; test de que cada ítem de “Hoy” enlaza a una ruta existente con el filtro correcto.
- La búsqueda global encuentra `P-000012`, `OC-000003`, `RT-000045`, `OT-P-000005-REV-A-03` y el nombre de un cliente (test e2e).
- Sin overflow horizontal entre 390 y 1920 (`ux:capture`); axe sin *serious*.
- Todos los deep links anteriores siguen funcionando (test de rutas).
