import type { TranslationKey } from "../../i18n/es-CL";
import type { OpeningChoice } from "./intentEditing";

/** Opening-grid options (D03): the legacy enums plus the spec ids every
 * emitted option key covers. The grid filters against the system's
 * `opening_options` — what the catalog does not declare is not offered. */
export const OPENING_OPTIONS: readonly [OpeningChoice, TranslationKey][] = [
  ["FIXED", "intent.fixed"],
  ["FIXED_SASH", "intent.fixedSash"],
  ["TURN_LEFT", "intent.turnLeft"],
  ["TURN_RIGHT", "intent.turnRight"],
  ["TURN_LEFT_OUT", "intent.turnLeftOut"],
  ["TURN_RIGHT_OUT", "intent.turnRightOut"],
  ["TILT_TURN_LEFT", "intent.tiltLeft"],
  ["TILT_TURN_RIGHT", "intent.tiltRight"],
  ["TILT", "intent.tilt"],
  ["BOTTOM_HUNG", "intent.bottomHung"],
  ["BOTTOM_HUNG_OUT", "intent.bottomHungOut"],
  ["AWNING", "intent.awning"],
  ["FRENCH_L", "intent.frenchL"],
  ["FRENCH_R", "intent.frenchR"],
  ["FRENCH_OUT_L", "intent.frenchOutL"],
  ["FRENCH_OUT_R", "intent.frenchOutR"],
  ["SLIDING_2L", "intent.sliding"],
  ["SLIDING_3L", "intent.sliding3"],
  ["SLIDING_4L", "intent.sliding4"],
  ["SLIDING", "intent.slidingLayout"],
  ["DOOR_ENTRY", "intent.door"],
  ["DOOR_LEFT_OUT", "intent.doorLeftOut"],
  ["DOOR_RIGHT_OUT", "intent.doorRightOut"],
  ["DOOR_DOUBLE", "intent.doorDouble"],
  ["DOOR_DOUBLE_L", "intent.doorDoubleL"],
];
