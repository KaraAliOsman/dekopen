/** Etiquetas de dominio — el mapa central §4. Todo enum que llega a la
 * pantalla tiene aquí su nombre en español y su tono; el chip de estado
 * nunca pinta un token crudo (`project.status` → «Aprobado», no
 * APPROVED). El test de exhaustividad (domainLabels.test.ts) rompe CI si
 * un enum nuevo aparece sin etiqueta: eso es a propósito — nombrar las
 * cosas ES el diseño.
 *
 * Tono = el color + icono del StatusChip; el color nunca va solo. */

export type DomainTone = "ok" | "warn" | "danger" | "info" | "person" | "neutral" | "unknown";

export type DomainLabel = {
  /** Nombre visible en español — vocabulario del glosario, no del enum. */
  label: string;
  tone: DomainTone;
  /** Icono del set ui/icons — opcional, nunca sustituye la etiqueta. */
  icon?: string;
};

type L = Record<string, DomainLabel>;
const l = (label: string, tone: DomainTone, icon?: string): DomainLabel => ({
  label,
  tone,
  ...(icon ? { icon } : {}),
});

/** Mapa: nombre del enum generado (orval) → valor → etiqueta.
 * Los valores faltantes se detectan en el test — este archivo es la fuente
 * de verdad editorial. */
export const DOMAIN_LABELS: Record<string, L> = {
  /* ---------- Hoy (urgencia de la cola por rol) ---------- */
  UrgencyEnum: {
    overdue: l("Atrasado", "person", "warn"),
    today: l("Hoy", "warn", "clock"),
    soon: l("Pronto", "info", "calendar"),
    when_free: l("Cuando puedas", "neutral"),
  },

  /* ---------- Proyecto / cotización ---------- */
  ProjectResponseStatusEnum: {
    DRAFT: l("Borrador", "neutral", "draft"),
    QUOTED: l("Cotizado", "info", "quote"),
    APPROVED: l("Aprobado", "ok", "check"),
    IN_PRODUCTION: l("En producción", "info", "station"),
    COMPLETED: l("Terminado", "ok", "check"),
    CANCELLED: l("Cancelado", "neutral", "cross"),
  },
  PriceResponseStateEnum: {
    PREVIEW: l("Vista previa", "neutral"),
    PENDING: l("Pendiente", "warn"),
    APPLIED: l("Aplicado", "ok", "check"),
    REJECTED: l("Rechazado", "danger", "cross"),
    WITHDRAWN: l("Retirado", "neutral"),
  },
  DecisionEnum: {
    APPROVED: l("Aprobado", "ok", "check"),
    DECLINED: l("Rechazado", "danger", "cross"),
  },

  /* ---------- Aperturas §3.6 ---------- */
  ImportOpeningTypeEnum: {
    AWNING: l("Proyectante", "info", "open-awning"),
    DOOR_ENTRY: l("Puerta de entrada", "info", "open-door"),
    FIXED: l("Fijo", "neutral", "open-fixed"),
    SLIDING_2L: l("Corredera de 2 hojas", "info", "open-sliding"),
    TILT_TURN_LEFT: l("Oscilobatiente izquierda", "info", "open-tilt-turn"),
    TILT_TURN_RIGHT: l("Oscilobatiente derecha", "info", "open-tilt-turn"),
    TURN_LEFT: l("Abatible izquierda", "info", "open-turn"),
    TURN_RIGHT: l("Abatible derecha", "info", "open-turn"),
  },
  KitOpeningTypeEnum: {
    AWNING: l("Proyectante", "info", "open-awning"),
    BOTTOM_HUNG: l("Abatimiento inferior", "info", "open-tilt-turn"),
    DOOR: l("Puerta", "info", "open-door"),
    FALLEBA: l("Falleba hoja pasiva", "info"),
    SLIDING: l("Corredera", "info", "open-sliding"),
    TILT: l("Banderola", "info", "open-tilt-turn"),
    TILT_TURN: l("Oscilobatiente", "info", "open-tilt-turn"),
    TURN: l("Abatible", "info", "open-turn"),
  },
  SlidingPanelFactsKindEnum: {
    MOVING: l("Hoja móvil", "info"),
    FIXED: l("Hoja fija", "neutral"),
  },
  OrientationEnum: {
    EXTERIOR_DOWN: l("Apertura abajo", "info"),
    EXTERIOR_UP: l("Apertura arriba", "info"),
    EXTERIOR_LEFT: l("Apertura izquierda", "info"),
    EXTERIOR_RIGHT: l("Apertura derecha", "info"),
  },
  SlidingTravelEnum: {
    LEFT: l("Izquierda", "neutral"),
    RIGHT: l("Derecha", "neutral"),
  },
  RailTypeEnum: {
    dual: l("Riel doble", "neutral"),
    mono: l("Riel simple", "neutral"),
  },

  /* ---------- Vano y montaje (D07) ---------- */
  MeasurementResponseStateEnum: {
    CLIENT_DECLARED: l("Medidas del cliente", "warn", "quote"),
    SITE_RECTIFIED: l("Rectificada en obra", "warn", "warn"),
    CONFIRMED: l("Confirmada para producción", "ok", "check"),
  },
  FabricationSourceEnum: {
    DERIVED: l("Derivada del vano", "info"),
    MANUAL_LOCK: l("Fijada a mano", "warn", "warn"),
    DECLARED: l("Declarada", "neutral"),
  },
  CodeEnum: {
    EN_VANO: l("En vano con holgura perimetral", "neutral"),
    PREMARCO: l("Con premarco", "neutral"),
    SOBRE_VANO: l("Sobre vano", "neutral"),
    TRASLAPADO: l("Traslapado", "neutral"),
    RENOVACION: l("Renovación sobre marco existente", "neutral"),
  },
  WallTypeEnum: {
    MASONRY: l("Albañilería", "neutral"),
    CONCRETE: l("Hormigón", "neutral"),
    PARTITION: l("Tabique", "neutral"),
    WOOD: l("Madera", "neutral"),
  },

  /* ---------- Producción ---------- */
  ProductionStepStatusEnum: {
    PENDING: l("Pendiente", "neutral"),
    READY: l("Lista", "info"),
    IN_PROGRESS: l("En curso", "info"),
    DONE: l("Terminado", "ok", "check"),
    BLOCKED: l("Bloqueado", "danger", "cross"),
  },
  WorkCenterRequestKindEnum: {
    CUT: l("Corte", "neutral", "station-cut"),
    PROFILE_CUT: l("Corte de perfil", "neutral", "station-cut"),
    REINFORCEMENT_CUT: l("Corte de refuerzo", "neutral", "station-cut"),
    MACHINING: l("Mecanizado", "neutral", "station-mill"),
    WELDING: l("Soldadura", "neutral", "station-weld"),
    CLEANING: l("Limpieza", "neutral", "station-clean"),
    CRIMPING: l("Engarzado", "neutral", "station-crimp"),
    SASH_ASSEMBLY: l("Armado de hoja", "neutral", "station-assembly"),
    ASSEMBLY: l("Ensamble", "neutral", "station-assembly"),
    HARDWARE: l("Herrajes", "neutral", "station-hardware"),
    GLAZING: l("Acristalamiento", "neutral", "station-glaze"),
    QC: l("Control de calidad", "neutral", "station-qc"),
    PACK: l("Embalaje", "neutral", "station-pack"),
  },
  QcResultEnum: {
    PASS: l("Conforme", "ok", "check"),
    FAIL: l("No conforme", "danger", "cross"),
  },
  StepTransitionRequestActionEnum: {
    START: l("Iniciar", "info"),
    COMPLETE: l("Completar", "ok"),
    BLOCK: l("Bloquear", "danger"),
    UNBLOCK: l("Desbloquear", "info"),
    NOTE: l("Nota", "neutral"),
    QC_CHECK: l("Control de calidad", "info"),
  },
  EngineInspectRequestModeEnum: {
    DESIGN: l("Diseño", "neutral"),
    WORKSHOP_QC: l("QC de taller", "info"),
  },
  /* §IA3 — provider state labels; the member-facing chip shows only
     mode/mock, and the OWNER settings card localizes through es-CL keys. */
  AiProviderModeEnum: {
    live: l("Proveedor real activo", "ok"),
    test: l("Modo de prueba", "warn"),
    partial: l("Configuración parcial", "warn"),
    unconfigured: l("Sin credencial", "danger"),
  },
  AiRouteModeEnum: {
    live: l("Proveedor real", "ok"),
    test: l("Modo de prueba", "warn"),
    unconfigured: l("Sin configurar", "danger"),
  },
  CutMaterialEnum: {
    PVC: l("PVC", "neutral"),
    ALUMINIUM: l("Aluminio", "neutral"),
    STEEL: l("Acero", "neutral"),
  },

  /* ---------- Inspector / errores técnicos ---------- */
  EngineInspectResponseStatusEnum: {
    GREEN: l("Sin observaciones", "ok", "check"),
    YELLOW: l("Observaciones", "warn", "warn"),
    RED: l("Bloqueado", "danger", "cross"),
  },
  InspectorFindingSeverityEnum: {
    YELLOW: l("Observación", "warn", "warn"),
    RED: l("Bloqueo", "danger", "cross"),
  },
  InspectorRuleIdEnum: {
    R01: l("Peso de hoja", "neutral"),
    R02: l("Proporción exterior", "neutral"),
    R03: l("Dimensiones terminadas", "neutral"),
    R04: l("Área de vidrio", "neutral"),
    R05: l("Refuerzo estructural", "neutral"),
    R06: l("Espesor de relleno", "neutral"),
    R07: l("Drenajes inferiores", "neutral"),
    R08: l("Puntos de cierre", "neutral"),
    R09: l("Largo continuo", "neutral"),
    R10: l("Medición de taller", "neutral"),
    R11: l("Holgura de cámara", "neutral"),
    R12: l("Corredera 3 hojas", "neutral"),
    R13: l("Brazos proyectante", "neutral"),
    R14: l("Capacidad de carro", "neutral"),
  },
  FixabilityEnum: {
    AUTO_FIXABLE: l("Corrección automática", "ok"),
    SUGGESTION_ONLY: l("Sugerencia", "warn"),
    BLOCKED_MISSING_AUTHORITY: l("Requiere autoridad", "person", "person"),
  },
  RuleEvaluationStatusEnum: {
    PASS: l("Conforme", "ok", "check"),
    FAIL: l("No conforme", "danger", "cross"),
    NOT_APPLICABLE: l("No aplica", "neutral"),
    MISSING_INPUT: l("Sin dato", "unknown"),
  },
  IntegrityEnum: {
    VERIFIED: l("Verificado", "ok", "check"),
    MISMATCH: l("No coincide", "danger", "cross"),
  },
  EngineAssemblyCalculateResponseStatusEnum: {
    VALID: l("Válido", "ok", "check"),
    MANUFACTURING_INCOMPLETE: l("Datos incompletos", "warn", "warn"),
    INVALID: l("Inválido", "danger", "cross"),
  },
  ProductIssueSeverityEnum: {
    error: l("Error", "danger", "cross"),
    warning: l("Advertencia", "warn", "warn"),
  },
  EdgesEnum: {
    top: l("superior", "neutral"),
    right: l("derecho", "neutral"),
    bottom: l("inferior", "neutral"),
    left: l("izquierdo", "neutral"),
  },
  GlassSafetyFindingSeverityEnum: {
    WARNING: l("Advertencia", "warn", "warn"),
    MANDATORY: l("Obligatorio", "danger", "cross"),
  },
  GlassSurchargeSelectionKindEnum: {
    EDGE_POLISH: l("Canto pulido", "neutral"),
    DRILL: l("Perforación", "neutral"),
    PALILLAJE: l("Palillaje", "neutral"),
  },

  /* ---------- Órdenes de compra / pagos ---------- */
  PlanStateEnum: {
    none: l("Sin plan", "neutral"),
    ok: l("Plan vigente", "ok", "check"),
    invalidated: l("Plan vencido", "warn", "warn"),
  },
  OrderStatusEnum: {
    DRAFT: l("Borrador", "neutral"),
    SENT: l("Enviada", "info"),
    PARTIALLY_RECEIVED: l("Recepción parcial", "warn"),
    FULFILLED: l("Recibida", "ok", "check"),
    CANCELLED: l("Cancelada", "neutral"),
  },
  OrderTypeEnum: {
    SUPPLIER_PROFILE_PO: l("Perfiles", "neutral"),
    SUPPLIER_GLASS_PO: l("Vidrio", "neutral"),
    SUPPLIER_HARDWARE_PO: l("Herrajes", "neutral"),
    SUPPLIER_PANEL_PO: l("Panel", "neutral"),
  },
  PaymentStatusEnum: {
    NO_DEAL: l("Sin acuerdo", "neutral"),
    PENDING: l("Por pagar", "warn"),
    PARTIAL: l("Pago parcial", "warn"),
    PAID: l("Pagado", "ok", "check"),
  },
  PaymentKindEnum: {
    ANTICIPO: l("Anticipo", "info"),
    PARCIAL: l("Pago parcial", "info"),
    SALDO: l("Saldo", "info"),
  },
  PaymentLinkStatusEnum: {
    DISPATCHING: l("Enviándose", "info"),
    PENDING: l("Pendiente", "warn"),
    PAID: l("Pagado", "ok", "check"),
    FAILED: l("Falló", "danger", "cross"),
    UNCERTAIN: l("Por confirmar", "warn", "warn"),
    CANCELLED: l("Anulado", "neutral"),
  },
  MethodEnum: {
    TRANSFER: l("Transferencia", "neutral"),
    CASH: l("Efectivo", "neutral"),
    CARD: l("Tarjeta", "neutral"),
    CHECK: l("Cheque", "neutral"),
    OTHER: l("Otro", "neutral"),
  },
  CurrencyEnum: {
    CLP: l("Peso chileno", "neutral"),
    USD: l("Dólar", "neutral"),
  },
  DeliveryStatusEnum: {
    SCHEDULED: l("Programada", "info"),
    ON_ROUTE: l("En ruta", "info"),
    DELIVERED: l("Entregada", "ok", "check"),
    FAILED: l("Fallida", "danger", "cross"),
  },
  DeliveryTransitionRequestStatusEnum: {
    ON_ROUTE: l("En ruta", "info"),
    DELIVERED: l("Entregada", "ok", "check"),
    FAILED: l("Fallida", "danger", "cross"),
  },
  TimeWindowEnum: {
    AM: l("Mañana", "neutral"),
    PM: l("Tarde", "neutral"),
    JORNADA: l("Jornada completa", "neutral"),
  },
  SiiEnvioStatusEnum: {
    PENDING: l("Pendiente", "warn"),
    ACCEPTED: l("Aceptado", "ok", "check"),
    REJECTED: l("Rechazado", "danger", "cross"),
  },

  /* ---------- Trabajos IA ---------- */
  JobRunStateEnum: {
    QUEUED: l("En cola", "neutral"),
    RUNNING: l("En curso", "info"),
    SUCCEEDED: l("Completado", "ok", "check"),
    FAILED: l("Falló", "danger", "cross"),
    CANCELED: l("Cancelado", "neutral"),
  },
  AiJobOutcomeActionEnum: {
    applied: l("Aplicado", "ok", "check"),
    declined: l("Descartado", "neutral"),
    apply_failed: l("Error al aplicar", "danger", "cross"),
  },
  AiAgentHistoryRoleEnum: {
    user: l("Usuario", "neutral"),
    agent: l("Asistente", "info"),
  },

  /* ---------- Roles / catálogo ---------- */
  MembershipRoleEnum: {
    OWNER: l("Dueño", "person", "person"),
    ESTIMATOR: l("Cotizador", "neutral"),
    WORKSHOP_MANAGER: l("Jefe de taller", "neutral"),
    INSTALLER: l("Instalador", "neutral"),
    OPERATOR: l("Operador", "neutral"),
  },
  CatalogProfileRoleEnum: {
    FRAME: l("Marco", "neutral"),
    SASH: l("Hoja", "neutral"),
    MULLION_V: l("Montante", "neutral"),
    MULLION_H: l("Travesaño", "neutral"),
    INVERSOR: l("Inversor", "neutral"),
    GLAZING_BEAD: l("Junquillo", "neutral"),
    COUPLER: l("Acoplador", "neutral"),
    ADDITIONAL: l("Adicional", "neutral"),
    THRESHOLD: l("Umbral", "neutral"),
  },
  SystemFamilyEnum: {
    CASEMENT: l("Abatibles", "neutral"),
    SLIDING: l("Corredera", "neutral"),
    LIFT_SLIDE: l("Corredera elevable", "neutral"),
    DOOR: l("Puerta", "neutral"),
    FACADE_FIXED: l("Fachada fija", "neutral"),
  },
  CatalogItemRoleEnum: {
    FRAME: l("Marco", "neutral"),
    SASH: l("Hoja", "neutral"),
    SLIDING_SASH: l("Hoja corredera", "neutral"),
    DOOR_SASH: l("Hoja de puerta", "neutral"),
    MULLION_V: l("Montante", "neutral"),
    MULLION_H: l("Travesaño", "neutral"),
    INTERLOCK: l("Contracierre", "neutral"),
    RAIL: l("Riel / guía", "neutral"),
    INVERSOR: l("Inversor", "neutral"),
    GLAZING_BEAD: l("Junquillo", "neutral"),
    COUPLER: l("Acoplador", "neutral"),
    ADDITIONAL: l("Adicional", "neutral"),
    THRESHOLD: l("Umbral", "neutral"),
    FRAME_EXTENSION: l("Alero de marco", "neutral"),
    SILL: l("Zócalo", "neutral"),
    COVER_TRIM: l("Tapa de contramarco", "neutral"),
    SKIRT: l("Faldón", "neutral"),
  },
  EntityEnum: {
    SYSTEM: l("Sistema", "neutral"),
    PROFILE: l("Perfil", "neutral"),
    CUT_RULE: l("Regla de corte", "neutral"),
    REINFORCEMENT_RULE: l("Regla de refuerzo", "neutral"),
    TYPOLOGY_LIMIT: l("Límite dimensional", "neutral"),
    FINISH: l("Color / acabado", "neutral"),
    GLAZING_RULE: l("Vidrio", "neutral"),
    HARDWARE_KIT: l("Kit de herrajes", "neutral"),
    HARDWARE_FAMILY: l("Familia de herraje", "neutral"),
    HANDLE_MODEL: l("Manilla", "neutral"),
    HANDLE_COLOR: l("Color de manilla", "neutral"),
    HARDWARE_OPTION: l("Opción de herraje", "neutral"),
    PRICE: l("Precio", "neutral"),
    GLASS_PRODUCT: l("Producto de vidrio", "neutral"),
    GLASS_SURCHARGE: l("Recargo de vidrio", "neutral"),
    GLASS_SAFETY_RULE: l("Seguridad de vidrio", "neutral"),
    GLASS_TYPE_LIMIT: l("Límite de vidrio", "neutral"),
    // D06
    EXTRA_ARTICLE: l("Accesorio / extra", "neutral"),
    SERVICE_ARTICLE: l("Servicio", "neutral"),
  },
  /* ---------- D06 accesorios y servicios ---------- */
  ExtraKindEnum: {
    SILL: l("Vierteaguas", "neutral"),
    FRAME_EXTENSION: l("Ensanche", "neutral"),
    COVER_TRIM: l("Tapajuntas", "neutral"),
    MOSQUITO_SCREEN: l("Mosquitero", "neutral"),
    VENTILATOR: l("Aireador", "neutral"),
  },
  ServiceKindEnum: {
    INSTALLATION: l("Instalación", "neutral"),
    SEALING: l("Sellado", "neutral"),
    REMOVAL: l("Retiro", "neutral"),
    SCAFFOLDING: l("Andamio", "neutral"),
    FREIGHT: l("Flete", "neutral"),
  },
  ExtrasDisplayEnum: {
    DETAILED: l("Detallado", "neutral"),
    GROUPED: l("Agrupado", "neutral"),
  },
  PieceOriginEnum: {
    PRODUCT: l("Producto", "neutral"),
    EXTRA: l("Extra", "neutral"),
  },
  PricingUnitEnum: {
    M: l("Metro", "neutral"),
    EA: l("Unidad", "neutral"),
  },
  QtyRuleEnum: {
    PER_LINEAR_METER: l("Por metro lineal", "neutral"),
    PER_M2: l("Por m²", "neutral"),
    PER_POSITION_UNIT: l("Por posición", "neutral"),
    FIXED: l("Fijo", "neutral"),
  },
  UnitKindsEnum: {
    WINDOW: l("Ventana", "neutral"),
    DOOR: l("Puerta", "neutral"),
  },
  /* ---------- D04 herrajes ---------- */
  AxisEnum: {
    WIDTH: l("Ancho", "neutral"),
    HEIGHT: l("Alto", "neutral"),
  },
  ComponentQtyRuleKindEnum: {
    PER_WIDTH: l("Por ancho de hoja", "neutral"),
    PER_HEIGHT: l("Por alto de hoja", "neutral"),
  },
  MachiningDeclarationKindEnum: {
    LOCK_PREP: l("Cerradero", "neutral"),
    HINGE_PREP: l("Alojamiento de bisagras", "neutral"),
    ESPAG_HOUSING: l("Alojamiento de cremona", "neutral"),
    DRAINAGE: l("Drenaje", "neutral"),
    OTHER: l("Otro", "neutral"),
  },
  MachiningDeclarationStatusEnum: {
    EMITTED: l("Emitida", "ok"),
    DECLARED_NOT_EMITTED: l("Declarada, no emitida", "warn"),
  },
  HardwareSelectionPriceSourceEnum: {
    HANDLE_MODEL: l("Modelo de manilla", "neutral"),
    HANDLE_COLOR: l("Color de manilla", "neutral"),
    OPTION: l("Opción", "neutral"),
  },
  CategoryEnum: {
    HANDLE: l("Manilla", "neutral"),
    HINGE: l("Bisagra", "neutral"),
    LOCK: l("Cerradura", "neutral"),
    ROLLER: l("Rodamiento", "neutral"),
    CONNECTOR: l("Conector", "neutral"),
    DRAINAGE: l("Drenaje", "neutral"),
    GASKET: l("Junta", "neutral"),
    SEAL: l("Sello", "neutral"),
    SCREW: l("Tornillo", "neutral"),
    CONSUMABLE: l("Insumo", "neutral"),
    FITTING: l("Herraje", "neutral"),
    SUPPORT: l("Soporte", "neutral"),
    CHANNEL: l("Canal", "neutral"),
    OTHER: l("Otro", "neutral"),
  },
  MaterialEnum: {
    PVC: l("PVC", "neutral"),
    ALUMINIUM: l("Aluminio", "neutral"),
  },
  ColorEnum: {
    WHITE: l("Blanco", "neutral"),
    FOILED: l("Foliado madera", "neutral"),
  },
  SegmentEnum: {
    RETAIL: l("Particular", "neutral"),
    ARCHITECT: l("Arquitecto", "neutral"),
    CONSTRUCTION: l("Constructora", "neutral"),
  },
  StockKindEnum: {
    BAR: l("Barra", "neutral"),
    SHEET: l("Plancha", "neutral"),
  },
  RemnantStatusEnum: {
    AVAILABLE: l("Disponible", "ok"),
    RESERVED: l("Reservado", "info"),
    CONSUMED: l("Consumido", "neutral"),
    SCRAPPED: l("Desechado", "neutral"),
  },
  RemnantOriginEnum: {
    RECEIPT: l("Recepción", "neutral"),
    PRODUCTION: l("Producción", "neutral"),
    MANUAL: l("Manual", "neutral"),
  },
  InventoryMovementMovementTypeEnum: {
    RECEIPT: l("Recepción", "ok"),
    RESERVATION: l("Reserva", "info"),
    RELEASE: l("Liberación", "info"),
    CONSUMPTION: l("Consumo", "neutral"),
    ADJUSTMENT: l("Ajuste", "warn"),
    RETURN: l("Devolución", "info"),
    SCRAP: l("Desecho", "danger"),
  },
  InventoryMovementRequestMovementTypeEnum: {
    ADJUSTMENT: l("Ajuste", "warn"),
    RETURN: l("Devolución", "info"),
    SCRAP: l("Desecho", "danger"),
  },
  PurchaseUnitEnum: {
    BAR: l("Barra", "neutral"),
  },
  AccessoryLineUnitEnum: {
    EA: l("unidad", "neutral"),
  },
  UnitEnum: {
    kit: l("kit", "neutral"),
  },
  EvidenceInputUnitEnum: {
    mm: l("mm", "neutral"),
    mm2: l("mm²", "neutral"),
    m: l("m", "neutral"),
    kg: l("kg", "neutral"),
    "kg/m": l("kg/m", "neutral"),
    "kg/m2": l("kg/m²", "neutral"),
    unit: l("unidad", "neutral"),
    set: l("juego", "neutral"),
    percent: l("%", "neutral"),
    currency: l("moneda", "neutral"),
    text: l("texto", "neutral"),
  },
  ExtraChargeKindEnum: {
    INSTALLATION: l("Instalación", "neutral"),
    FREIGHT: l("Flete", "neutral"),
    OTHER: l("Otro", "neutral"),
  },
  ObligationKindEnum: {
    SEALING: l("Sellado", "neutral"),
    FASTENING: l("Fijación", "neutral"),
    DRAINAGE: l("Drenaje", "neutral"),
    INSTALLATION_ACCESSORY: l("Accesorio de instalación", "neutral"),
    OTHER_DECLARED: l("Otro declarado", "neutral"),
  },
  PricingModeEnum: {
    COST_PLUS_MARGIN: l("Costo + margen", "neutral"),
    PRICE_PER_M2_BY_TYPOLOGY: l("Precio por m² según tipología", "neutral"),
    FIXED_PRICE_MATRIX_DIMENSIONAL: l("Matriz fija por dimensión", "neutral"),
    TARGET_GROSS_MARGIN_PROJECT: l("Margen bruto objetivo", "neutral"),
    COMMERCIAL_LIST_WITH_DISCOUNTS: l("Lista comercial con descuentos", "neutral"),
  },
  DataProvenanceEnum: {
    SEED_SYNTHETIC: l("Dato de muestra", "neutral"),
    MANUAL: l("Ingreso manual", "neutral"),
    IMPORT: l("Importado", "neutral"),
    LEGACY_UNVERIFIED: l("Sin verificar", "warn", "warn"),
  },
  AuthorityTableEnum: {
    catalog_imports: l("Importaciones de catálogo", "neutral"),
    fitting_purchase_mappings: l("Equivalencias de herrajes", "neutral"),
    glass_purchase_mappings: l("Equivalencias de vidrio", "neutral"),
    glazing_bead_matrix: l("Matriz de junquillos", "neutral"),
    handle_requirement_policies: l("Políticas de manillas", "neutral"),
    hardware_kits: l("Kits de herraje", "neutral"),
    infill_articles: l("Rellenos", "neutral"),
    manufacturing_placement_policies: l("Políticas de ubicación", "neutral"),
    profile_articles: l("Artículos de perfil", "neutral"),
    profile_systems: l("Sistemas de perfil", "neutral"),
    reinforcement_cut_policies: l("Políticas de corte de refuerzo", "neutral"),
  },
  ScopeEnum: {
    SYSTEM: l("Sistema", "neutral"),
    SERIES: l("Serie", "neutral"),
    GLOBAL: l("Global", "neutral"),
    ORG: l("Organización", "neutral"),
  },
  SectionSourceEnum: {
    POLYGON: l("Polígono", "neutral"),
    DXF_REFERENCE: l("Referencia DXF", "neutral"),
  },
  LocalOriginEnum: {
    TOP_LEFT: l("Esquina superior izquierda", "neutral"),
    TOP_RIGHT: l("Esquina superior derecha", "neutral"),
    BOTTOM_LEFT: l("Esquina inferior izquierda", "neutral"),
    BOTTOM_RIGHT: l("Esquina inferior derecha", "neutral"),
    CENTROID: l("Centroide", "neutral"),
  },
  VerticalReferenceEnum: {
    OUTER_TOP: l("Borde superior exterior", "neutral"),
    OUTER_BOTTOM: l("Borde inferior exterior", "neutral"),
    LEAF_TOP: l("Borde superior de hoja", "neutral"),
    LEAF_BOTTOM: l("Borde inferior de hoja", "neutral"),
  },
  ChangeEnum: {
    ADDED: l("Agregado", "ok"),
    REMOVED: l("Quitado", "danger"),
    CHANGED: l("Modificado", "warn"),
  },
  DrainFixRuleIdEnum: {
    R07: l("Drenajes inferiores", "neutral"),
  },
  DrainOperationKindEnum: {
    ADD_BOTTOM_DRAIN_HOLE: l("Agregar drenaje inferior", "neutral"),
  },
  BarAuthoritySourceEnum: {
    PROFILE: l("Perfil", "neutral"),
    REINFORCEMENT: l("Refuerzo", "neutral"),
  },
  CoverageEnum: {
    DECLARED: l("Declarado", "neutral"),
    NONE_REQUIRED: l("No requerido", "neutral"),
  },
  ReviewStateEnum: {
    REVIEWED: l("Revisado", "ok", "check"),
    REJECTED: l("Rechazado", "danger", "cross"),
  },
  ArtifactScopeEnum: {
    PROJECT_REVISION: l("Revisión de proyecto", "neutral"),
    ORDER: l("Orden", "neutral"),
  },
  FormatEnum: {
    PDF: l("PDF", "neutral"),
    XLSX: l("Planilla", "neutral"),
  },
  EnvironmentEnum: {
    sandbox: l("Ambiente de pruebas", "neutral"),
    production: l("Producción", "neutral"),
  },
  RequiredAalEnum: {
    aal2: l("Verificación reforzada", "info"),
  },
  CreditLotOriginEnum: {
    trial: l("Prueba", "neutral"),
    monthly: l("Mensual", "neutral"),
    pack: l("Pack", "neutral"),
    legacy: l("Heredado", "neutral"),
  },
  StrategyEnum: {
    fast: l("Rápido", "neutral"),
    deep: l("Profundo", "neutral"),
    auto: l("Automático", "neutral"),
  },
  /* ---------- Acabados (D05) ---------- */
  ColorSurchargeApplicationKindEnum: {
    PER_PROFILE_METER: l("Por metro de perfil", "neutral"),
    PER_M2: l("Por m²", "neutral"),
    FIXED_PER_POSITION: l("Fijo por posición", "neutral"),
    PCT_OF_MATERIALS: l("% sobre materiales", "neutral"),
  },
  BasisUnitEnum: {
    M: l("Metro lineal", "neutral"),
    M2: l("m²", "neutral"),
    POSITION: l("Posición", "neutral"),
    MATERIALS_PCT: l("% de materiales", "neutral"),
  },
  /* ---------- Documentos por organización ---------- */
  DocPaperSizeEnum: {
    LETTER: l("Carta", "neutral"),
    LEGAL: l("Oficio", "neutral"),
    A4: l("A4", "neutral"),
  },
};

/** Enums que NUNCA llegan a una pantalla — contratos internos del API.
 * Aparecer aquí exige justificación: si el enum puede pintarse en la UI,
 * pertenece al mapa de arriba. */
export const ENUM_INTERNAL: readonly string[] = [
  "AalEnum",
  "ApiUrlEnum",
  "DecimalSeparatorEnum",
  "DocumentTypeEnum",
  "IndTrasladoEnum",
  "NullEnum",
];

/** Etiqueta de un valor de enum — el nombre del enum (export orval) y el
 * valor. Si falta, devuelve el valor crudo con tono desconocido: el test
 * de exhaustividad impide que esto llegue a producción sin etiqueta. */
export function domainLabel(enumName: string, value: string): DomainLabel {
  const found = DOMAIN_LABELS[enumName]?.[value];
  if (found) return found;
  return { label: value, tone: "unknown" };
}
