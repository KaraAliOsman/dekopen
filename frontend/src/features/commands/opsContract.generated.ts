// GENERADO por scripts/gen_ops_contract.py — la fuente es
// backend/projects/ops_registry.py; no editar a mano.
/* eslint-disable prettier/prettier */

export const OPS_CONTRACT_VERSION = 2 as const;

export type OpsScope = "position" | "product" | "project";

export type OpsContractOpName = "set_module_count" | "add_unit" | "remove_unit" | "duplicate_module" | "add_stacked_unit" | "insert_module" | "remove_coupling" | "set_coupling_kind" | "set_module_width" | "set_total_width" | "set_height" | "equalize_widths" | "equalize_angles" | "set_coupling_angle" | "split_bay" | "equalize_bays" | "set_bay_size" | "move_divider" | "remove_divider" | "remove_bay" | "set_opening" | "flip_handing" | "set_handle_height" | "set_sliding_layout" | "set_travel" | "set_glass" | "set_glass_thickness" | "set_panel" | "set_system" | "set_finish" | "set_location" | "set_quantity" | "add_position" | "duplicate_position" | "remove_position" | "update_position";

export interface OpsContractParam {
  name: string;
  kind: string;
  required: boolean;
  enum: string[];
  numeric: boolean;
  ref: string;
  allow_wildcard: boolean;
  nullable: boolean;
  catalog: string;
  description: string;
}

export interface OpsContractEntry {
  name: OpsContractOpName;
  scope: OpsScope;
  batchable: boolean;
  structural: boolean;
  description: string;
  params: OpsContractParam[];
  examples: Record<string, unknown>[];
}

export const OPS_CONTRACT: {
  version: number;
  scopes: OpsScope[];
  ops: OpsContractEntry[];
  schema: Record<string, unknown>;
} = {
  "version": 2,
  "scopes": [
    "position",
    "product",
    "project"
  ],
  "ops": [
    {
      "name": "set_module_count",
      "scope": "product",
      "batchable": false,
      "structural": false,
      "description": "Reconfigurar el conjunto a N módulos iguales acoplados en línea",
      "params": [
        {
          "name": "count",
          "kind": "int",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "1..12"
        }
      ],
      "examples": [
        {
          "op": "set_module_count",
          "count": 2
        }
      ]
    },
    {
      "name": "add_unit",
      "scope": "product",
      "batchable": false,
      "structural": true,
      "description": "Agregar una unidad al extremo (izquierda o derecha) del conjunto",
      "params": [
        {
          "name": "side",
          "kind": "enum",
          "required": true,
          "enum": [
            "left",
            "right"
          ],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        }
      ],
      "examples": [
        {
          "op": "add_unit",
          "side": "right"
        }
      ]
    },
    {
      "name": "remove_unit",
      "scope": "product",
      "batchable": false,
      "structural": true,
      "description": "Quitar un módulo del conjunto (sella la junta que quedaba libre)",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        }
      ],
      "examples": []
    },
    {
      "name": "duplicate_module",
      "scope": "product",
      "batchable": false,
      "structural": true,
      "description": "Duplicar un módulo pegado a su derecha (misma especificación)",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        }
      ],
      "examples": []
    },
    {
      "name": "add_stacked_unit",
      "scope": "product",
      "batchable": false,
      "structural": true,
      "description": "Apilar una unidad encima de un módulo (banderola sobre puerta/ventana)",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "height_mm",
          "kind": "mm",
          "required": false,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "alto de la unidad superior; omitir usa el default del editor"
        }
      ],
      "examples": []
    },
    {
      "name": "insert_module",
      "scope": "product",
      "batchable": false,
      "structural": true,
      "description": "Insertar un módulo en medio de dos unidades acopladas (sobre su unión)",
      "params": [
        {
          "name": "coupling",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "coupling",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la unión (acople) entre módulos"
        }
      ],
      "examples": []
    },
    {
      "name": "remove_coupling",
      "scope": "product",
      "batchable": false,
      "structural": true,
      "description": "Separar una unión: el conjunto se divide en dos subconjuntos",
      "params": [
        {
          "name": "coupling",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "coupling",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la unión (acople) entre módulos"
        }
      ],
      "examples": []
    },
    {
      "name": "set_coupling_kind",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Cambiar el tipo de unión (INLINE en línea, STACKED apilado, TEE en T, CORNER en esquina)",
      "params": [
        {
          "name": "coupling",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "coupling",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la unión (acople) entre módulos"
        },
        {
          "name": "kind",
          "kind": "enum",
          "required": true,
          "enum": [
            "INLINE",
            "STACKED",
            "TEE",
            "CORNER"
          ],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "set_module_width",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Fijar el ancho de un módulo (los demás conservan su medida)",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "width_mm",
          "kind": "mm",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        }
      ],
      "examples": [
        {
          "op": "set_module_width",
          "module": "m1",
          "width_mm": "900"
        }
      ]
    },
    {
      "name": "set_total_width",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Escalar todos los anchos para que el conjunto mida el total pedido",
      "params": [
        {
          "name": "width_mm",
          "kind": "mm",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "set_height",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Fijar el alto de todos los módulos del conjunto",
      "params": [
        {
          "name": "height_mm",
          "kind": "mm",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "equalize_widths",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Igualar el ancho de todos los módulos del conjunto",
      "params": [],
      "examples": []
    },
    {
      "name": "equalize_angles",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Igualar los ángulos de todas las uniones (reparte el giro total)",
      "params": [],
      "examples": []
    },
    {
      "name": "set_coupling_angle",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Fijar el ángulo de una unión (esquina/bow); redondeo a 0,1°",
      "params": [
        {
          "name": "coupling",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "coupling",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la unión (acople) entre módulos"
        },
        {
          "name": "angle_deg",
          "kind": "deg",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "split_bay",
      "scope": "product",
      "batchable": false,
      "structural": true,
      "description": "Dividir una hoja de un módulo con montante (axis V) o travesaño (axis H). offset_mm se mide desde el borde inicial del vano según 'from' (START=izquierda/arriba, END=derecha/abajo, CENTER=centrado); parts=N divide la hoja en N partes iguales (el número debe venir del pedido — 'en tres hojas' declara 3); mullion_sku puede omitirse si el catálogo tiene un único perfil para ese eje",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "bay",
          "kind": "ref",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
        },
        {
          "name": "axis",
          "kind": "enum",
          "required": true,
          "enum": [
            "V",
            "H"
          ],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        },
        {
          "name": "offset_mm",
          "kind": "mm",
          "required": false,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "posición del eje del montante/travesaño; omitir = centrar"
        },
        {
          "name": "from",
          "kind": "enum",
          "required": false,
          "enum": [
            "START",
            "END",
            "CENTER"
          ],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "desde dónde se mide offset_mm (default START)"
        },
        {
          "name": "parts",
          "kind": "int",
          "required": false,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "N partes iguales (2..8) — sustituye offset_mm; el count debe estar declarado en el pedido"
        },
        {
          "name": "mullion_sku",
          "kind": "sku",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "mullions",
          "description": "SKU del poste/travesaño; por defecto el del catálogo para el eje"
        }
      ],
      "examples": [
        {
          "op": "split_bay",
          "module": "m1",
          "axis": "V",
          "offset_mm": "750"
        },
        {
          "op": "split_bay",
          "module": "m1",
          "bay": "m1/b2",
          "axis": "H",
          "from": "CENTER"
        },
        {
          "op": "split_bay",
          "module": "m1",
          "axis": "V",
          "parts": 3
        }
      ]
    },
    {
      "name": "equalize_bays",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Igualar las hojas de un módulo (reparte el vano entre las divisiones)",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        }
      ],
      "examples": []
    },
    {
      "name": "set_bay_size",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Fijar la medida de una hoja dentro de su división (ancho con axis V, alto con axis H); la hoja vecina absorbe la diferencia. En un módulo de una sola hoja equivale a cambiar su ancho/alto",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "bay",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        },
        {
          "name": "mm",
          "kind": "mm",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        },
        {
          "name": "axis",
          "kind": "enum",
          "required": false,
          "enum": [
            "V",
            "H"
          ],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "omitir usa el eje de la división padre"
        }
      ],
      "examples": []
    },
    {
      "name": "move_divider",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Mover un montante/travesaño existente a otro offset del vano",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "divider",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "divider",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        },
        {
          "name": "offset_mm",
          "kind": "mm",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "remove_divider",
      "scope": "product",
      "batchable": false,
      "structural": true,
      "description": "Quitar un montante/travesaño: sus dos hojas se fusionan (keep_bay elige cuál sobrevive; por defecto la primera)",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "divider",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "divider",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        },
        {
          "name": "keep_bay",
          "kind": "ref",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "hoja que conserva su especificación al fusionar"
        }
      ],
      "examples": []
    },
    {
      "name": "remove_bay",
      "scope": "product",
      "batchable": false,
      "structural": true,
      "description": "Eliminar una hoja de un módulo dividido (la hoja vecina ocupa el vano)",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "bay",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "set_opening",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Cambiar la apertura de las hojas del módulo — o solo de una hoja si se pasa 'bay'. El valor es una key de catalog.openings (las aperturas que el sistema admite) — nunca un nombre libre",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "bay",
          "kind": "ref",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
        },
        {
          "name": "opening",
          "kind": "string",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "openings",
          "description": ""
        }
      ],
      "examples": [
        {
          "op": "set_opening",
          "module": "m1",
          "opening": "TILT_TURN_LEFT"
        },
        {
          "op": "set_opening",
          "module": "m1",
          "bay": "m1/b2",
          "opening": "FIXED"
        }
      ]
    },
    {
      "name": "flip_handing",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Espejar la hoja: manilla al lado opuesto (TURN↔, TILT_TURN↔, hoja primaria de corredera, dirección de puerta)",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "bay",
          "kind": "ref",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
        }
      ],
      "examples": []
    },
    {
      "name": "set_handle_height",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Fijar la altura de la manilla (mm) sobre una hoja. Solo si el dato es inequívoco; si la referencia es ambigua (¿desde el vano? ¿desde el piso?) pregunta con clarify en vez de operar",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "bay",
          "kind": "ref",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
        },
        {
          "name": "mm",
          "kind": "mm",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "altura de la manilla"
        }
      ],
      "examples": []
    },
    {
      "name": "set_sliding_layout",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Fijar la configuración de corredera (preset SLIDING_2L/3L/4L o 'layout' completo) sobre una hoja corredera",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "bay",
          "kind": "ref",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
        },
        {
          "name": "preset",
          "kind": "enum",
          "required": false,
          "enum": [
            "SLIDING_2L",
            "SLIDING_3L",
            "SLIDING_4L"
          ],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        },
        {
          "name": "primary_index",
          "kind": "int",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "índice de la hoja que corre primero (0-based)"
        }
      ],
      "examples": []
    },
    {
      "name": "set_travel",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Cambiar qué hoja de la corredera es la que corre (panel móvil↔fijo)",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "bay",
          "kind": "ref",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
        },
        {
          "name": "slot",
          "kind": "int",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "posición del panel (0-based)"
        },
        {
          "name": "kind",
          "kind": "enum",
          "required": true,
          "enum": [
            "MOVING",
            "FIXED"
          ],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "set_glass",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Cambiar el vidrio de las hojas del módulo — o de una hoja con 'bay'. sku es el SKU de catálogo (catalog.glass_skus); 'recipe' permite pedir por receta declarada (catalog.glass_recipes, p.ej. '4-12-4')",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "bay",
          "kind": "ref",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
        },
        {
          "name": "sku",
          "kind": "sku",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "glass",
          "description": ""
        },
        {
          "name": "recipe",
          "kind": "string",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "glass",
          "description": "receta declarada del vidrio cuando no hay SKU a mano"
        }
      ],
      "examples": []
    },
    {
      "name": "set_glass_thickness",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Cambiar el espesor de acristalamiento (mm) — debe estar en catalog.thicknesses para que el sistema lo acristale",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "bay",
          "kind": "ref",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
        },
        {
          "name": "mm",
          "kind": "mm",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "thicknesses",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "set_panel",
      "scope": "product",
      "batchable": true,
      "structural": false,
      "description": "Poner o quitar el panel sándwich de las hojas (sku=null lo quita)",
      "params": [
        {
          "name": "module",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "module",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref del módulo del producto (product.modules[].ref)"
        },
        {
          "name": "bay",
          "kind": "ref",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "bay",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
        },
        {
          "name": "sku",
          "kind": "sku",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": true,
          "catalog": "panel",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "set_system",
      "scope": "position",
      "batchable": false,
      "structural": false,
      "description": "Cambiar la serie del diseño (catalog.systems lista las elegibles; cambiar de material/familia puede invalidar la tipología)",
      "params": [
        {
          "name": "system_id",
          "kind": "uuid",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "systems",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "set_finish",
      "scope": "position",
      "batchable": false,
      "structural": false,
      "description": "Cambiar el acabado/color de la posición (catalog.finishes)",
      "params": [
        {
          "name": "color",
          "kind": "string",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "finishes",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "set_location",
      "scope": "position",
      "batchable": false,
      "structural": false,
      "description": "Asignar la etiqueta de ubicación de la posición (Dormitorio, Baño…)",
      "params": [
        {
          "name": "location",
          "kind": "string",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "texto libre, máx. 100"
        }
      ],
      "examples": []
    },
    {
      "name": "set_quantity",
      "scope": "position",
      "batchable": false,
      "structural": false,
      "description": "Cambiar la cantidad de unidades de la posición",
      "params": [
        {
          "name": "count",
          "kind": "int",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "1..9999"
        }
      ],
      "examples": []
    },
    {
      "name": "add_position",
      "scope": "project",
      "batchable": false,
      "structural": false,
      "description": "Crear una posición nueva en el proyecto con dimensiones y apertura iniciales (borrador que la persona revisa en la superficie real)",
      "params": [
        {
          "name": "width_mm",
          "kind": "mm",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        },
        {
          "name": "height_mm",
          "kind": "mm",
          "required": true,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        },
        {
          "name": "location",
          "kind": "string",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        },
        {
          "name": "opening",
          "kind": "string",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "openings",
          "description": ""
        },
        {
          "name": "system_id",
          "kind": "uuid",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "systems",
          "description": ""
        },
        {
          "name": "quantity",
          "kind": "int",
          "required": false,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "duplicate_position",
      "scope": "project",
      "batchable": false,
      "structural": false,
      "description": "Duplicar una posición existente (mismo diseño, nuevo índice)",
      "params": [
        {
          "name": "position_id",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "position",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "id de la posición del proyecto (visible en el contexto)"
        },
        {
          "name": "count",
          "kind": "int",
          "required": false,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        }
      ],
      "examples": []
    },
    {
      "name": "remove_position",
      "scope": "project",
      "batchable": false,
      "structural": false,
      "description": "Eliminar una posición del proyecto",
      "params": [
        {
          "name": "position_id",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "position",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "id de la posición del proyecto (visible en el contexto)"
        }
      ],
      "examples": []
    },
    {
      "name": "update_position",
      "scope": "project",
      "batchable": false,
      "structural": false,
      "description": "Actualizar campos de una posición: ubicación, cantidad, sistema o acabado (cada campo opcional, al menos uno requerido)",
      "params": [
        {
          "name": "position_id",
          "kind": "ref",
          "required": true,
          "enum": [],
          "numeric": false,
          "ref": "position",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": "id de la posición del proyecto (visible en el contexto)"
        },
        {
          "name": "location",
          "kind": "string",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        },
        {
          "name": "quantity",
          "kind": "int",
          "required": false,
          "enum": [],
          "numeric": true,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "",
          "description": ""
        },
        {
          "name": "system_id",
          "kind": "uuid",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "systems",
          "description": ""
        },
        {
          "name": "finish",
          "kind": "string",
          "required": false,
          "enum": [],
          "numeric": false,
          "ref": "",
          "allow_wildcard": false,
          "nullable": false,
          "catalog": "finishes",
          "description": ""
        }
      ],
      "examples": []
    }
  ],
  "schema": {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "title": "DekopenDesignOps",
    "version": 2,
    "ops": {
      "set_module_count": {
        "type": "object",
        "required": [
          "op",
          "count"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_module_count"
          },
          "count": {
            "type": "integer",
            "description": "1..12"
          }
        }
      },
      "add_unit": {
        "type": "object",
        "required": [
          "op",
          "side"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "add_unit"
          },
          "side": {
            "type": "string",
            "enum": [
              "left",
              "right"
            ]
          }
        }
      },
      "remove_unit": {
        "type": "object",
        "required": [
          "op",
          "module"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "remove_unit"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          }
        }
      },
      "duplicate_module": {
        "type": "object",
        "required": [
          "op",
          "module"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "duplicate_module"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          }
        }
      },
      "add_stacked_unit": {
        "type": "object",
        "required": [
          "op",
          "module"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "add_stacked_unit"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "height_mm": {
            "type": "string",
            "description": "número decimal como string (mm) alto de la unidad superior; omitir usa el default del editor"
          }
        }
      },
      "insert_module": {
        "type": "object",
        "required": [
          "op",
          "coupling"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "insert_module"
          },
          "coupling": {
            "type": "string",
            "description": "ref de la unión (acople) entre módulos"
          }
        }
      },
      "remove_coupling": {
        "type": "object",
        "required": [
          "op",
          "coupling"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "remove_coupling"
          },
          "coupling": {
            "type": "string",
            "description": "ref de la unión (acople) entre módulos"
          }
        }
      },
      "set_coupling_kind": {
        "type": "object",
        "required": [
          "op",
          "coupling",
          "kind"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_coupling_kind"
          },
          "coupling": {
            "type": "string",
            "description": "ref de la unión (acople) entre módulos"
          },
          "kind": {
            "type": "string",
            "enum": [
              "INLINE",
              "STACKED",
              "TEE",
              "CORNER"
            ]
          }
        }
      },
      "set_module_width": {
        "type": "object",
        "required": [
          "op",
          "module",
          "width_mm"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_module_width"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "width_mm": {
            "type": "string",
            "description": "número decimal como string (mm)"
          }
        }
      },
      "set_total_width": {
        "type": "object",
        "required": [
          "op",
          "width_mm"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_total_width"
          },
          "width_mm": {
            "type": "string",
            "description": "número decimal como string (mm)"
          }
        }
      },
      "set_height": {
        "type": "object",
        "required": [
          "op",
          "height_mm"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_height"
          },
          "height_mm": {
            "type": "string",
            "description": "número decimal como string (mm)"
          }
        }
      },
      "equalize_widths": {
        "type": "object",
        "required": [
          "op"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "equalize_widths"
          }
        }
      },
      "equalize_angles": {
        "type": "object",
        "required": [
          "op"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "equalize_angles"
          }
        }
      },
      "set_coupling_angle": {
        "type": "object",
        "required": [
          "op",
          "coupling",
          "angle_deg"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_coupling_angle"
          },
          "coupling": {
            "type": "string",
            "description": "ref de la unión (acople) entre módulos"
          },
          "angle_deg": {
            "type": "string",
            "description": "número decimal como string (mm)"
          }
        }
      },
      "split_bay": {
        "type": "object",
        "required": [
          "op",
          "module",
          "axis"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "split_bay"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "bay": {
            "type": "string",
            "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
          },
          "axis": {
            "type": "string",
            "enum": [
              "V",
              "H"
            ]
          },
          "offset_mm": {
            "type": "string",
            "description": "número decimal como string (mm) posición del eje del montante/travesaño; omitir = centrar"
          },
          "from": {
            "type": "string",
            "enum": [
              "START",
              "END",
              "CENTER"
            ],
            "description": "desde dónde se mide offset_mm (default START)"
          },
          "parts": {
            "type": "integer",
            "description": "N partes iguales (2..8) — sustituye offset_mm; el count debe estar declarado en el pedido"
          },
          "mullion_sku": {
            "type": "string",
            "description": "SKU del poste/travesaño; por defecto el del catálogo para el eje"
          }
        }
      },
      "equalize_bays": {
        "type": "object",
        "required": [
          "op",
          "module"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "equalize_bays"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          }
        }
      },
      "set_bay_size": {
        "type": "object",
        "required": [
          "op",
          "module",
          "bay",
          "mm"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_bay_size"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "bay": {
            "type": "string"
          },
          "mm": {
            "type": "string",
            "description": "número decimal como string (mm)"
          },
          "axis": {
            "type": "string",
            "enum": [
              "V",
              "H"
            ],
            "description": "omitir usa el eje de la división padre"
          }
        }
      },
      "move_divider": {
        "type": "object",
        "required": [
          "op",
          "module",
          "divider",
          "offset_mm"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "move_divider"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "divider": {
            "type": "string"
          },
          "offset_mm": {
            "type": "string",
            "description": "número decimal como string (mm)"
          }
        }
      },
      "remove_divider": {
        "type": "object",
        "required": [
          "op",
          "module",
          "divider"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "remove_divider"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "divider": {
            "type": "string"
          },
          "keep_bay": {
            "type": "string",
            "description": "hoja que conserva su especificación al fusionar"
          }
        }
      },
      "remove_bay": {
        "type": "object",
        "required": [
          "op",
          "module",
          "bay"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "remove_bay"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "bay": {
            "type": "string"
          }
        }
      },
      "set_opening": {
        "type": "object",
        "required": [
          "op",
          "module",
          "opening"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_opening"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "bay": {
            "type": "string",
            "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
          },
          "opening": {
            "type": "string"
          }
        }
      },
      "flip_handing": {
        "type": "object",
        "required": [
          "op",
          "module"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "flip_handing"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "bay": {
            "type": "string",
            "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
          }
        }
      },
      "set_handle_height": {
        "type": "object",
        "required": [
          "op",
          "module",
          "mm"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_handle_height"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "bay": {
            "type": "string",
            "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
          },
          "mm": {
            "type": "string",
            "description": "número decimal como string (mm) altura de la manilla"
          }
        }
      },
      "set_sliding_layout": {
        "type": "object",
        "required": [
          "op",
          "module"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_sliding_layout"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "bay": {
            "type": "string",
            "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
          },
          "preset": {
            "type": "string",
            "enum": [
              "SLIDING_2L",
              "SLIDING_3L",
              "SLIDING_4L"
            ]
          },
          "primary_index": {
            "type": "integer",
            "description": "índice de la hoja que corre primero (0-based)"
          }
        }
      },
      "set_travel": {
        "type": "object",
        "required": [
          "op",
          "module",
          "slot",
          "kind"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_travel"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "bay": {
            "type": "string",
            "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
          },
          "slot": {
            "type": "integer",
            "description": "posición del panel (0-based)"
          },
          "kind": {
            "type": "string",
            "enum": [
              "MOVING",
              "FIXED"
            ]
          }
        }
      },
      "set_glass": {
        "type": "object",
        "required": [
          "op",
          "module"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_glass"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "bay": {
            "type": "string",
            "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
          },
          "sku": {
            "type": "string"
          },
          "recipe": {
            "type": "string",
            "description": "receta declarada del vidrio cuando no hay SKU a mano"
          }
        }
      },
      "set_glass_thickness": {
        "type": "object",
        "required": [
          "op",
          "module",
          "mm"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_glass_thickness"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "bay": {
            "type": "string",
            "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
          },
          "mm": {
            "type": "string",
            "description": "número decimal como string (mm)"
          }
        }
      },
      "set_panel": {
        "type": "object",
        "required": [
          "op",
          "module",
          "sku"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_panel"
          },
          "module": {
            "type": "string",
            "description": "ref del módulo del producto (product.modules[].ref)"
          },
          "bay": {
            "type": "string",
            "description": "ref de la hoja/bahía dentro del módulo; omitir = todas o la principal"
          },
          "sku": {
            "anyOf": [
              {
                "type": "string"
              },
              {
                "type": "null"
              }
            ]
          }
        }
      },
      "set_system": {
        "type": "object",
        "required": [
          "op",
          "system_id"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_system"
          },
          "system_id": {
            "type": "string"
          }
        }
      },
      "set_finish": {
        "type": "object",
        "required": [
          "op",
          "color"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_finish"
          },
          "color": {
            "type": "string"
          }
        }
      },
      "set_location": {
        "type": "object",
        "required": [
          "op",
          "location"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_location"
          },
          "location": {
            "type": "string",
            "description": "texto libre, máx. 100"
          }
        }
      },
      "set_quantity": {
        "type": "object",
        "required": [
          "op",
          "count"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "set_quantity"
          },
          "count": {
            "type": "integer",
            "description": "1..9999"
          }
        }
      },
      "add_position": {
        "type": "object",
        "required": [
          "op",
          "width_mm",
          "height_mm"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "add_position"
          },
          "width_mm": {
            "type": "string",
            "description": "número decimal como string (mm)"
          },
          "height_mm": {
            "type": "string",
            "description": "número decimal como string (mm)"
          },
          "location": {
            "type": "string"
          },
          "opening": {
            "type": "string"
          },
          "system_id": {
            "type": "string"
          },
          "quantity": {
            "type": "integer"
          }
        }
      },
      "duplicate_position": {
        "type": "object",
        "required": [
          "op",
          "position_id"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "duplicate_position"
          },
          "position_id": {
            "type": "string",
            "description": "id de la posición del proyecto (visible en el contexto)"
          },
          "count": {
            "type": "integer"
          }
        }
      },
      "remove_position": {
        "type": "object",
        "required": [
          "op",
          "position_id"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "remove_position"
          },
          "position_id": {
            "type": "string",
            "description": "id de la posición del proyecto (visible en el contexto)"
          }
        }
      },
      "update_position": {
        "type": "object",
        "required": [
          "op",
          "position_id"
        ],
        "additionalProperties": false,
        "properties": {
          "op": {
            "const": "update_position"
          },
          "position_id": {
            "type": "string",
            "description": "id de la posición del proyecto (visible en el contexto)"
          },
          "location": {
            "type": "string"
          },
          "quantity": {
            "type": "integer"
          },
          "system_id": {
            "type": "string"
          },
          "finish": {
            "type": "string"
          }
        }
      }
    }
  }
};
