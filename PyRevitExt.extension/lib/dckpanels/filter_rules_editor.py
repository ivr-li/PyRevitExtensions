# -*- coding: utf-8 -*-
"""Filter rules editor — modal WPF window for editing ParameterFilterElement rules."""

import traceback

import clr

clr.AddReference("System")
clr.AddReference("PresentationCore")
clr.AddReference("PresentationFramework")
clr.AddReference("WindowsBase")
clr.AddReference("System.Xml")
clr.AddReference("RevitAPI")
import System.Windows as WinNS
import System.Windows.Controls as Controls
import System.Xml
from Autodesk.Revit.DB import *
from pyrevit import forms
from pyrevit.forms import WPFWindow
from System import EventHandler
from System.Collections.Generic import List
from System.Collections.ObjectModel import ObservableCollection
from System.ComponentModel import INotifyPropertyChanged, PropertyChangedEventArgs
from System.IO import StringReader
from System.Windows.Data import CollectionViewSource
from System.Windows.Markup import XamlReader
from System.Xml import XmlReader

from dckpanels.graphics_override_editor import (
    GRAPHICS_TAB_XAML,
    GraphicsOverrideModel,
    build_override_settings,
    clear_pattern_caches,
    read_graphics_from_ui,
    setup_graphics_tab,
)

# =================== Operator definitions ===================
STRING_OPERATORS = [
    ("равно", "str_equals"),
    ("не равно", "str_not_equals"),
    ("содержит", "str_contains"),
    ("не содержит", "str_not_contains"),
    ("начинается с", "str_begins"),
    ("заканчивается на", "str_ends"),
]
NUMERIC_OPERATORS = [
    ("равно", "num_equals"),
    ("не равно", "num_not_equals"),
    ("больше", "num_greater"),
    ("больше или равно", "num_greater_eq"),
    ("меньше", "num_less"),
    ("меньше или равно", "num_less_eq"),
]
COMMON_OPERATORS = [
    ("имеет значение", "has_value"),
    ("не имеет значения", "has_no_value"),
]

STORAGE_TYPE_MAP = {
    StorageType.String: "string",
    StorageType.Double: "number",
    StorageType.Integer: "number",
    StorageType.ElementId: "element_id",
}

YESNO_CHOICES = ["Да", "Нет"]

_yesno_pids = set()


# =================== YesNo detection ===================
def _is_yesno_spec(spec_type_id):
    """Check if ForgeTypeId spec represents a boolean (YesNo) parameter."""
    if not spec_type_id:
        return False
    try:
        type_str = spec_type_id.TypeId
        if not type_str:
            return False
        return "yesno" in type_str.lower() or "boolean" in type_str.lower()
    except (AttributeError, Exception):
        return False


def _cache_yesno_param(param, cid_int):
    """Cache Integer param as YesNo if its spec indicates boolean."""
    if param.StorageType != StorageType.Integer:
        return
    defn = param.Definition
    if not defn:
        return
    spec = _get_definition_data_type(defn)
    if _is_yesno_spec(spec):
        _yesno_pids.add(param.Id.IntegerValue)


def _check_is_yesno(param_id, spec_type_id=None):
    """Check if parameter is YesNo. Shared params use spec, BIPs use cache."""
    pid = param_id.IntegerValue
    if pid >= 0 and spec_type_id:
        return _is_yesno_spec(spec_type_id)
    return pid in _yesno_pids


# =================== Unit Keywords Fallback ===================
UNIT_KEYWORDS = [
    (["AREA", "ПЛОЩ", "SQUARE", "SURFACE"], "area"),
    (["VOLUME", "ОБЪЕМ", "VOLUM", "CUBIC", "MASS"], "volume"),
    (["ANGLE", "УГОЛ", "ROTATION", "DIRECTION", "BEARING"], "angle"),
    (["FORCE", "СИЛА", "LOAD", "WEIGHT", "NEWTON"], "force"),
    (["TEMPERATURE", "TEMP", "НАГР"], "temperature"),
    (["TIME", "DURATION", "ВРЕМЯ"], "time"),
    (["COST", "PRICE", "СТОИМ"], "cost"),
    (
        [
            "LENGTH",
            "WIDTH",
            "HEIGHT",
            "ELEV",
            "OFFSET",
            "DIST",
            "LONG",
            "ШИР",
            "ВЫС",
            "ДЛИН",
            "ТОЛЩ",
            "THICK",
            "DIAMETER",
            "RADIUS",
        ],
        "length",
    ),
    (["URL", "PATH", "NAME", "NUMBER", "TEXT", "DESC", "MARK"], "string"),
]


def _get_unit_type_from_keywords(param_name):
    """Определить тип единицы по ключевым словам в имени параметра."""
    if not param_name:
        return None
    name_upper = param_name.upper()
    for keywords, unit_type in UNIT_KEYWORDS:
        if any(k in name_upper for k in keywords):
            return unit_type
    return None


def _get_unit_type_id_from_keyword(param_name):
    """Вернуть ForgeTypeId UnitTypeId по ключевым словам."""
    unit_type = _get_unit_type_from_keywords(param_name)
    if not unit_type or unit_type == "string":
        return None
    attr_map = {
        "length": "Millimeters",
        "area": "SquareMeters",
        "volume": "CubicMeters",
        "angle": "Degrees",
        "force": "Newtons",
        "temperature": "Celsius",
        "time": "Minutes",
        "cost": "Currency",
    }
    attr_name = attr_map.get(unit_type)
    if not attr_name:
        return None
    return getattr(UnitTypeId, attr_name, None)


# =================== Parameter info wrapper ===================
class ParameterInfo(object):
    """Wraps a parameter ElementId with its display name and storage type."""

    def __init__(
        self,
        name,
        param_id,
        storage_type="string",
        spec_type_id=None,
        unit_type_id=None,
    ):
        self.name = name
        self.param_id = param_id
        self.storage_type = storage_type
        self.spec_type_id = spec_type_id
        self.unit_type_id = unit_type_id  # Новое поле: ForgeTypeId единицы (мм, м², м³)

    def __str__(self):
        return self.name


class OperatorInfo(object):
    """Wraps operator display name and internal key."""

    def __init__(self, display_name, key):
        self.display_name = display_name
        self.key = key

    def __str__(self):
        return self.display_name


# =================== Data models ===================
class CategoryCheckItem(INotifyPropertyChanged):
    """Category checkbox item for the editor."""

    def __init__(self, name, category_id, is_checked=False):
        self._name = name
        self._category_id = category_id
        self._is_checked = is_checked
        self._propertyChanged = None

    @property
    def Name(self):
        return self._name

    @property
    def CategoryId(self):
        return self._category_id

    @property
    def IsChecked(self):
        return self._is_checked

    @IsChecked.setter
    def IsChecked(self, value):
        if self._is_checked != value:
            self._is_checked = value
            self._raise("IsChecked")

    def add_PropertyChanged(self, handler):
        self._propertyChanged = EventHandler.Combine(self._propertyChanged, handler)

    def remove_PropertyChanged(self, handler):
        self._propertyChanged = EventHandler.Remove(self._propertyChanged, handler)

    def _raise(self, prop):
        if self._propertyChanged:
            self._propertyChanged(self, PropertyChangedEventArgs(prop))


class RuleItem(INotifyPropertyChanged):
    """Single filter rule in the editor."""

    def __init__(
        self,
        param_info=None,
        operator_info=None,
        value="",
        available_params=None,
        param_type="string",
    ):
        self._selected_parameter = param_info
        self._selected_operator = operator_info
        self._value = value
        self._param_type = param_type
        self._available_params = available_params or []
        self._available_operators = self._build_operators(param_type)
        self._propertyChanged = None

    def _build_operators(self, param_type):
        """Build operator list based on parameter type."""
        ops = []
        if param_type == "element_id":
            ops.append(OperatorInfo("равно", "eid_equals"))
            ops.append(OperatorInfo("не равно", "eid_not_equals"))
        elif param_type == "string":
            for name, key in STRING_OPERATORS:
                ops.append(OperatorInfo(name, key))
        else:
            for name, key in NUMERIC_OPERATORS:
                ops.append(OperatorInfo(name, key))
            for name, key in COMMON_OPERATORS:
                ops.append(OperatorInfo(name, key))
        return ops

    @property
    def SelectedParameter(self):
        return self._selected_parameter

    @SelectedParameter.setter
    def SelectedParameter(self, value):
        if self._selected_parameter != value:
            self._selected_parameter = value
            if value:
                new_type = value.storage_type
                if new_type != self._param_type:
                    self._param_type = new_type
                    self._available_operators = self._build_operators(new_type)
                    self._raise("AvailableOperators")
                    if self._available_operators:
                        self._selected_operator = self._available_operators[0]
                        self._raise("SelectedOperator")
            self._raise("SelectedParameter")

    @property
    def SelectedOperator(self):
        return self._selected_operator

    @SelectedOperator.setter
    def SelectedOperator(self, value):
        if self._selected_operator != value:
            self._selected_operator = value
            self._raise("SelectedOperator")
            self._raise("IsValueVisible")

    @property
    def Value(self):
        return self._value

    @Value.setter
    def Value(self, value):
        if self._value != value:
            self._value = value
            self._raise("Value")

    @property
    def AvailableParameters(self):
        return self._available_params

    @property
    def AvailableOperators(self):
        return self._available_operators

    @property
    def IsValueVisible(self):
        if not self._selected_operator:
            return True
        return self._selected_operator.key not in ("has_value", "has_no_value")

    def add_PropertyChanged(self, handler):
        self._propertyChanged = EventHandler.Combine(self._propertyChanged, handler)

    def remove_PropertyChanged(self, handler):
        self._propertyChanged = EventHandler.Remove(self._propertyChanged, handler)

    def _raise(self, prop):
        if self._propertyChanged:
            self._propertyChanged(self, PropertyChangedEventArgs(prop))


# =================== Unit conversion helpers ===================
def _get_definition_data_type(definition):
    """Get ForgeTypeId from parameter definition (Revit 2021+/2022+ compat)."""
    try:
        return definition.GetDataType()
    except (AttributeError, Exception):
        pass
    try:
        return definition.GetSpecTypeId()
    except (AttributeError, Exception):
        pass
    return None


def _get_display_unit(doc, spec_type_id):
    """Get UnitTypeId for document's display unit of a spec, or None."""
    if not doc or not spec_type_id:
        return None
    try:
        if not UnitUtils.IsMeasurableSpec(spec_type_id):
            return None
        fmt = doc.GetUnits().GetFormatOptions(spec_type_id)
        return fmt.GetUnitTypeId()
    except Exception:
        return None


def _parse_number(value):
    """Parse string to float, default 0."""
    try:
        return float(value)
    except (ValueError, TypeError):
        return 0.0


_unit_cache = {}


def _build_unit_cache_for_category(doc, category_id):
    """Cache UnitTypeId for ALL Double params on first element of category."""
    cid_int = category_id.IntegerValue
    if cid_int in _unit_cache:
        return
    _unit_cache[cid_int] = {}
    for getter in (
        lambda: (
            FilteredElementCollector(doc)
            .OfCategoryId(category_id)
            .WhereElementIsNotElementType()
            .FirstElement()
        ),
        lambda: (
            FilteredElementCollector(doc)
            .OfCategoryId(category_id)
            .WhereElementIsElementType()
            .FirstElement()
        ),
    ):
        elem = getter()
        if not elem:
            continue
        for param in elem.Parameters:
            pid = param.Id.IntegerValue
            _cache_yesno_param(param, cid_int)
            if pid in _unit_cache[cid_int]:
                continue
            if param.StorageType != StorageType.Double:
                continue
            try:
                uid = param.GetUnitTypeId()
                if uid and uid != UnitTypeId.InvalidUnitId:
                    _unit_cache[cid_int][pid] = uid
            except Exception:
                pass


def _find_unit_on_element(doc, category_id, target_pid):
    """Find UnitTypeId from cached element parameters."""
    _build_unit_cache_for_category(doc, category_id)
    return _unit_cache.get(category_id.IntegerValue, {}).get(target_pid)


def _resolve_unit_type_id(
    doc, param_id, category_ids, param_name="", spec_type_id=None
):
    """
    Универсальный поиск UnitTypeId:
    1. Через FormatOptions документа (если есть spec_type_id)
    2. Через сэмпл элемента (самый надежный для BuiltIn)
    3. Через ключевые слова в имени параметра
    """
    # 1. Попытка через spec_type_id и настройки документа
    if spec_type_id:
        try:
            if UnitUtils.IsMeasurableSpec(spec_type_id):
                fmt = doc.GetUnits().GetFormatOptions(spec_type_id)
                if fmt:
                    unit_id = fmt.GetUnitTypeId()
                    if unit_id and unit_id != UnitTypeId.InvalidUnitId:
                        return unit_id
        except:
            pass

    # 2. Via sample element — iterate elem.Parameters (get_Parameter returns None for many BIPs)
    if category_ids:
        target = param_id.IntegerValue
        for cid in category_ids:
            unit_id = _find_unit_on_element(doc, cid, target)
            if unit_id:
                return unit_id

    # 3. Fallback по ключевым словам
    unit_id = _get_unit_type_id_from_keyword(param_name)
    if unit_id:
        return unit_id

    return None


def _to_internal(value_str, doc, param_info, category_ids=None):
    """Convert display-unit value string to Revit internal units."""
    num = _parse_number(value_str)

    # Берем unit_type_id из param_info
    unit_id = param_info.unit_type_id

    # Если единица не найдена, пытаемся определить сейчас
    if not unit_id and doc and category_ids:
        unit_id = _resolve_unit_type_id(
            doc,
            param_info.param_id,
            category_ids,
            param_name=param_info.name,
            spec_type_id=param_info.spec_type_id,
        )

    if not unit_id:
        print(
            "WARN _to_internal: no unit for '{}' (pid={}), saving raw".format(
                param_info.name, param_info.param_id.IntegerValue
            )
        )
        return num

    try:
        return UnitUtils.ConvertToInternalUnits(num, unit_id)
    except Exception:
        return num


def _from_internal(internal_val, doc, unit_type_id, storage_type="number"):
    """Convert Revit internal units to display-unit string."""
    if storage_type in ("string", "element_id"):
        return str(internal_val)

    if not unit_type_id:
        return str(internal_val)

    try:
        converted = UnitUtils.ConvertFromInternalUnits(internal_val, unit_type_id)
        return "{:.6f}".format(converted).rstrip("0").rstrip(".")
    except Exception:
        return str(internal_val)


# =================== ElementId dropdown ===================
_eid_choices_cache = {}


def _find_sample_eid_value(doc, param_id, category_ids):
    """Find a real ElementId value from elements for the given parameter."""
    pid_int = param_id.IntegerValue
    # 1. Try BIP via get_Parameter
    if pid_int < 0:
        bip = BuiltInParameter(pid_int)
        for cid in category_ids or []:
            elem = (
                FilteredElementCollector(doc)
                .OfCategoryId(cid)
                .WhereElementIsNotElementType()
                .FirstElement()
            )
            if not elem:
                continue
            p = elem.get_Parameter(bip)
            if p and p.StorageType == StorageType.ElementId:
                val = p.AsElementId()
                if val and val != ElementId.InvalidElementId:
                    return val
    # 2. Scan first element of each category
    for cid in category_ids or []:
        elem = (
            FilteredElementCollector(doc)
            .OfCategoryId(cid)
            .WhereElementIsNotElementType()
            .FirstElement()
        )
        if not elem:
            continue
        for p in elem.Parameters:
            if p.Id.IntegerValue != pid_int:
                continue
            if p.StorageType == StorageType.ElementId:
                val = p.AsElementId()
                if val and val != ElementId.InvalidElementId:
                    return val
    # 3. Scan document without category filter
    collector = FilteredElementCollector(doc).WhereElementIsNotElementType()
    for elem in collector:
        for p in elem.Parameters:
            if p.Id.IntegerValue != pid_int:
                continue
            if p.StorageType == StorageType.ElementId:
                val = p.AsElementId()
                if val and val != ElementId.InvalidElementId:
                    return val
    return None


def _collect_eid_by_class_detection(doc, sample_eid):
    """Detect .NET class of element referenced by sample_eid."""
    if not sample_eid or sample_eid == ElementId.InvalidElementId:
        return None
    elem = doc.GetElement(sample_eid)
    if not elem:
        return None
    return type(elem)


def _collect_elements_of_class(doc, element_class):
    """Collect all elements of a given class."""
    if not element_class:
        return []
    result = []
    try:
        collector = FilteredElementCollector(doc).OfClass(element_class)
        for elem in collector:
            name = getattr(elem, "Name", None)
            if name:
                result.append((name, elem.Id))
    except Exception:
        pass
    result.sort(key=lambda x: x[0])
    return result


def _collect_eid_choices(doc, param_id, category_ids):
    """Get list of (name, ElementId) for ElementId parameter dropdown."""
    cache_key = (param_id.IntegerValue, tuple(c.IntegerValue for c in category_ids))
    if cache_key in _eid_choices_cache:
        return _eid_choices_cache[cache_key]
    sample = _find_sample_eid_value(doc, param_id, category_ids)
    if not sample:
        _eid_choices_cache[cache_key] = []
        return []
    elem_class = _collect_eid_by_class_detection(doc, sample)
    choices = _collect_elements_of_class(doc, elem_class)
    _eid_choices_cache[cache_key] = choices
    return choices


# =================== Parameter storage info ===================
_bip_cache = {}


def _get_bip_storage_info(doc, param_id, category_ids=None):
    """Get (storage_type_str, spec_type_id) for a BuiltInParameter"""
    int_val = param_id.IntegerValue
    if int_val in _bip_cache:
        return _bip_cache[int_val]
    bip = BuiltInParameter(int_val)
    st_str, spec = _resolve_bip_via_forge(doc, bip)
    # print("DEBUG_get_bip_storage_info: bip {} | st_str {} | spec {}".format(bip, st_str, spec))
    _bip_cache[int_val] = (st_str, spec)
    return (st_str, spec)


def _resolve_bip_via_forge(doc, bip):
    """Resolve storage type and spec via ParameterUtils"""
    stmap = STORAGE_TYPE_MAP
    try:
        forge_id = ParameterUtils.GetParameterTypeId(bip)
        st = doc.GetTypeOfStorage(forge_id)
        st_str = stmap.get(st, "string")
        spec = _get_spec_from_forge_id(forge_id, st_str)
        return (st_str, spec)
    except (AttributeError, Exception):
        pass
    return ("string", None)


def _get_spec_from_forge_id(forge_id, storage_type):
    """Check if ForgeTypeId is a measurable spec (has physical units)"""
    if storage_type != "number" or not forge_id:
        # print("storage have been passed")
        return None
    try:
        if UnitUtils.IsMeasurableSpec(forge_id):
            return forge_id
    except Exception:
        pass
    return None


def _get_param_storage_info(doc, param_id, category_ids):
    """Return (storage_type_str, spec_type_id, unit_type_id)"""
    try:
        param_name = _get_param_name(doc, param_id)
        if param_id.IntegerValue < 0:
            storage, spec = _get_bip_storage_info(doc, param_id, category_ids)
        else:
            storage, spec = _get_param_storage_info_shared(doc, param_id)

        # Определяем unit_type_id
        unit_id = _resolve_unit_type_id(doc, param_id, category_ids, param_name, spec)
        return (storage, spec, unit_id)
    except Exception:
        return ("string", None, None)


def _get_param_storage_info_shared(doc, param_id):
    """Resolve storage info for shared/project parameter."""
    param_elem = doc.GetElement(param_id)
    if not param_elem:
        return ("string", None)
    definition = param_elem.GetDefinition()
    if not definition:
        return ("string", None)
    spec = _get_definition_data_type(definition)
    if not spec:
        return ("string", None)
    # YesNo params are Integer but not measurable
    if _is_yesno_spec(spec):
        return ("number", spec)
    try:
        if UnitUtils.IsMeasurableSpec(spec):
            return ("number", spec)
    except Exception:
        pass
    return ("string", None)


def _resolve_spec_type(doc, param_id, category_ids=None):
    """Get ForgeTypeId spec for a parameter (used during rule parsing)."""
    try:
        int_val = param_id.IntegerValue
        if int_val >= 0:
            param_elem = doc.GetElement(param_id)
            if param_elem:
                defn = param_elem.GetDefinition()
                if defn:
                    return _get_definition_data_type(defn)
            return None
        result = _get_bip_storage_info(doc, param_id, category_ids)
        return result[1]
    except Exception:
        pass
    return None


# =================== Rule parsing ===================
def _get_param_name(doc, param_id):
    """Get parameter display name from ElementId."""
    int_val = param_id.IntegerValue
    if int_val < 0:
        try:
            bip = BuiltInParameter(int_val)
            return LabelUtils.GetLabelFor(bip)
        except Exception:
            return "Параметр [{}]".format(int_val)
    elem = doc.GetElement(param_id)
    if elem:
        return elem.Name
    return "Параметр [{}]".format(int_val)


def _get_storage_type(rule):
    """Determine storage type from rule class."""
    if isinstance(rule, FilterStringRule):
        return "string"
    if isinstance(rule, (FilterDoubleRule, FilterIntegerRule)):
        return "number"
    if isinstance(rule, FilterElementIdRule):
        return "element_id"
    return "string"


def _identify_operator(rule):
    """Parse a FilterRule into an OperatorInfo key."""
    if isinstance(rule, HasNoValueFilterRule):
        return "has_no_value"
    if isinstance(rule, HasValueFilterRule):
        return "has_value"
    is_inverse = isinstance(rule, FilterInverseRule)
    inner_rule = rule.GetInnerRule() if is_inverse else rule
    if isinstance(inner_rule, FilterStringRule):
        return _identify_string_operator(inner_rule, is_inverse)
    if isinstance(inner_rule, FilterElementIdRule):
        return "eid_not_equals" if is_inverse else "eid_equals"
    if isinstance(inner_rule, (FilterDoubleRule, FilterIntegerRule)):
        return _identify_numeric_operator(inner_rule, is_inverse)
    return "str_equals"


def _identify_string_operator(inner_rule, is_inverse):
    """Identify string operator key from rule evaluator."""
    evaluator = inner_rule.GetEvaluator()
    ev_type = type(evaluator).__name__
    mapping = {
        "FilterStringEquals": "str_equals",
        "FilterStringContains": "str_contains",
        "FilterStringBeginsWith": "str_begins",
        "FilterStringEndsWith": "str_ends",
    }
    key = mapping.get(ev_type, "str_equals")
    if is_inverse:
        inverse_map = {
            "str_equals": "str_not_equals",
            "str_contains": "str_not_contains",
        }
        key = inverse_map.get(key, key)
    return key


def _identify_numeric_operator(inner_rule, is_inverse):
    """Identify numeric operator key from rule evaluator."""
    evaluator = inner_rule.GetEvaluator()
    ev_type = type(evaluator).__name__
    mapping = {
        "FilterNumericEquals": "num_equals",
        "FilterNumericGreater": "num_greater",
        "FilterNumericGreaterOrEqual": "num_greater_eq",
        "FilterNumericLess": "num_less",
        "FilterNumericLessOrEqual": "num_less_eq",
    }
    key = mapping.get(ev_type, "num_equals")
    if is_inverse and key == "num_equals":
        key = "num_not_equals"
    return key


def _get_rule_value(
    rule,
    doc=None,
    spec_type_id=None,
    unit_type_id=None,
    storage_type="number",
    param_name="",
):
    """Extract the value from a FilterRule as string"""
    if isinstance(rule, (HasNoValueFilterRule, HasValueFilterRule)):
        return ""
    inner = rule.GetInnerRule() if isinstance(rule, FilterInverseRule) else rule
    if isinstance(inner, FilterStringRule):
        return inner.RuleString or ""
    if isinstance(inner, FilterDoubleRule):
        # Если unit_type_id не передан, пытаемся определить
        if not unit_type_id and storage_type == "number":
            if spec_type_id:
                unit_type_id = _get_display_unit(doc, spec_type_id)
            if not unit_type_id and param_name:
                unit_type_id = _get_unit_type_id_from_keyword(param_name)
        if not unit_type_id:
            return str(inner.RuleValue)
        return _from_internal(inner.RuleValue, doc, unit_type_id, storage_type)
    if isinstance(inner, FilterIntegerRule):
        param_id = inner.GetRuleParameter()
        if _check_is_yesno(param_id, spec_type_id):
            return "Да" if inner.RuleValue else "Нет"
        return str(inner.RuleValue)
    if isinstance(inner, FilterElementIdRule):
        return _resolve_element_name(doc, inner.RuleValue)
    return ""


def _resolve_element_name(doc, elem_id):
    """Resolve ElementId to element name."""
    if not doc or not elem_id or elem_id == ElementId.InvalidElementId:
        return str(elem_id.IntegerValue) if elem_id else ""
    elem = doc.GetElement(elem_id)
    if not elem:
        return str(elem_id.IntegerValue)
    name = getattr(elem, "Name", None)
    return name if name else str(elem_id.IntegerValue)


def _get_rule_param_id(rule):
    """Get parameter ElementId from rule."""
    if isinstance(rule, (HasNoValueFilterRule, HasValueFilterRule)):
        return rule.GetRuleParameter()
    inner = rule.GetInnerRule() if isinstance(rule, FilterInverseRule) else rule
    return inner.GetRuleParameter()


def parse_element_filter(doc, pfe):
    """Parse ParameterFilterElement into (logic_type, list_of_rule_dicts)."""
    cat_ids = list(pfe.GetCategories())
    elem_filter = pfe.GetElementFilter()
    if elem_filter is None:
        return ("and", [])
    rules_data = []
    logic = "and"
    if isinstance(elem_filter, ElementParameterFilter):
        rules_data = _parse_param_filter(doc, elem_filter, cat_ids)
    elif isinstance(elem_filter, LogicalAndFilter):
        logic = "and"
        for sub in elem_filter.GetFilters():
            if isinstance(sub, ElementParameterFilter):
                rules_data.extend(_parse_param_filter(doc, sub, cat_ids))
            else:
                return None
    elif isinstance(elem_filter, LogicalOrFilter):
        logic = "or"
        for sub in elem_filter.GetFilters():
            if isinstance(sub, ElementParameterFilter):
                rules_data.extend(_parse_param_filter(doc, sub, cat_ids))
            else:
                return None
    else:
        return None
    return (logic, rules_data)


def _parse_param_filter(doc, epf, category_ids=None):
    """Parse ElementParameterFilter into list of rule dicts."""
    results = []
    for rule in epf.GetRules():
        param_id = _get_rule_param_id(rule)
        storage = _get_storage_type(rule)
        spec = _resolve_spec_type(doc, param_id, category_ids)
        param_name = _get_param_name(doc, param_id)
        # Fast unit resolve — spec + keywords only, no element scanning
        unit_id = _get_display_unit(doc, spec)
        if not unit_id:
            unit_id = _get_unit_type_id_from_keyword(param_name)
        results.append(
            {
                "param_id": param_id,
                "param_name": param_name,
                "operator_key": _identify_operator(rule),
                "value": _get_rule_value(rule, doc, spec, unit_id, storage, param_name),
                "storage_type": storage,
                "spec_type_id": spec,
                "unit_type_id": unit_id,
            }
        )
    return results


# =================== Rule building ===================
def _create_evaluator(key):
    """Create evaluator from operator key."""
    mapping = {
        "str_equals": FilterStringEquals(),
        "str_contains": FilterStringContains(),
        "str_begins": FilterStringBeginsWith(),
        "str_ends": FilterStringEndsWith(),
        "num_equals": FilterNumericEquals(),
        "num_greater": FilterNumericGreater(),
        "num_greater_eq": FilterNumericGreaterOrEqual(),
        "num_less": FilterNumericLess(),
        "num_less_eq": FilterNumericLessOrEqual(),
    }
    return mapping.get(key)


def _find_element_by_name(doc, name):
    """Find ElementId by element name. Returns InvalidElementId if not found."""
    if not doc or not name:
        return ElementId.InvalidElementId
    try:
        int_id = int(name)
        return ElementId(int_id)
    except (ValueError, TypeError):
        pass
    collector = FilteredElementCollector(doc).WhereElementIsNotElementType()
    for elem in collector:
        if getattr(elem, "Name", None) == name:
            return elem.Id
    collector_t = FilteredElementCollector(doc).WhereElementIsElementType()
    for elem in collector_t:
        if getattr(elem, "Name", None) == name:
            return elem.Id
    return ElementId.InvalidElementId


def _build_single_rule(rule_item, doc=None, category_ids=None):
    """Build a FilterRule from a RuleItem."""
    key = rule_item.SelectedOperator.key
    param_id = rule_item.SelectedParameter.param_id
    provider = ParameterValueProvider(param_id)
    value = rule_item.Value or ""
    # Convert YesNo display value to integer
    spec = rule_item.SelectedParameter.spec_type_id
    if _check_is_yesno(param_id, spec):
        int_val = 1 if value == "Да" else 0
        evaluator = FilterNumericEquals()
        inner = FilterIntegerRule(provider, evaluator, int_val)
        if key in ("num_not_equals", "eid_not_equals"):
            return FilterInverseRule(inner)
        return inner
    if key == "has_value":
        return HasValueFilterRule(param_id)
    if key == "has_no_value":
        return HasNoValueFilterRule(param_id)
    if key in ("eid_equals", "eid_not_equals"):
        return _build_eid_rule(provider, key, doc, value)
    if key == "str_not_equals":
        inner = FilterStringRule(provider, FilterStringEquals(), value)
        return FilterInverseRule(inner)
    if key == "str_not_contains":
        inner = FilterStringRule(provider, FilterStringContains(), value)
        return FilterInverseRule(inner)
    if key == "num_not_equals":
        num_val = _to_internal(value, doc, rule_item.SelectedParameter, category_ids)
        inner = FilterDoubleRule(provider, FilterNumericEquals(), num_val, 1e-6)
        return FilterInverseRule(inner)
    evaluator = _create_evaluator(key)
    if not evaluator:
        return None
    if key.startswith("str_"):
        return FilterStringRule(provider, evaluator, value)
    # Numeric rules — convert to internal units
    num_val = _to_internal(value, doc, rule_item.SelectedParameter, category_ids)
    # print("DEBUG_build_rule: param={}, value={}, unit={}, internal={}".format(
    #     rule_item.SelectedParameter.name, value, rule_item.SelectedParameter.unit_type_id, num_val))
    return FilterDoubleRule(provider, evaluator, num_val, 1e-6)


def _build_eid_rule(provider, key, doc, value):
    """Build ElementId filter rule."""
    eid = _find_element_by_name(doc, value)
    inner = FilterElementIdRule(provider, FilterNumericEquals(), eid)
    if key == "eid_not_equals":
        return FilterInverseRule(inner)
    return inner


def build_element_filter(rule_items, is_and, doc=None, category_ids=None):
    """Build ElementFilter from list of RuleItems."""
    if not rule_items:
        return None
    filters = []
    for ri in rule_items:
        if not ri.SelectedParameter or not ri.SelectedOperator:
            continue
        rule = _build_single_rule(ri, doc, category_ids)
        if rule:
            filters.append(ElementParameterFilter(rule))
    if not filters:
        return None
    if len(filters) == 1:
        return filters[0]
    if is_and:
        return LogicalAndFilter(filters)
    return LogicalOrFilter(filters)


# =================== Available parameters ===================
def get_filterable_parameters(doc, category_ids, lightweight=False):
    """Get list of ParameterInfo for categories.
    lightweight=True skips unit resolution (fast open, resolve on save).
    """
    params = []
    try:
        cat_list = List[ElementId](category_ids)
        param_ids = ParameterFilterUtilities.GetFilterableParametersInCommon(
            doc, cat_list
        )
        for pid in param_ids:
            name = _get_param_name(doc, pid)
            if lightweight:
                storage, spec = _get_storage_and_spec_fast(doc, pid)
                params.append(ParameterInfo(name, pid, storage, spec, None))
            else:
                storage, spec, unit_id = _get_param_storage_info(doc, pid, category_ids)
                params.append(ParameterInfo(name, pid, storage, spec, unit_id))
    except Exception:
        print(traceback.format_exc())
    params.sort(key=lambda p: p.name)
    return params


def _get_storage_and_spec_fast(doc, param_id):
    """Get (storage_type_str, spec_type_id) without scanning elements."""
    if param_id.IntegerValue < 0:
        return _get_bip_storage_info(doc, param_id)
    return _get_param_storage_info_shared(doc, param_id)


# =================== XAML ===================
EDITOR_XAML = """
<Window xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
Title="Настройки фильтра"
Width="850" Height="650"
WindowStartupLocation="CenterScreen"
Background="#F5F5F5">
<Window.Resources>
<BooleanToVisibilityConverter x:Key="BoolToVis"/>
</Window.Resources>
<Grid Margin="12">
<Grid.RowDefinitions>
<RowDefinition Height="Auto"/>
<RowDefinition Height="*"/>
<RowDefinition Height="Auto"/>
<RowDefinition Height="Auto"/>
</Grid.RowDefinitions>
<!-- Filter name -->
<Grid Grid.Row="0" Margin="0,0,0,10">
<Grid.ColumnDefinitions>
<ColumnDefinition Width="Auto"/>
<ColumnDefinition Width="*"/>
</Grid.ColumnDefinitions>
<TextBlock Grid.Column="0"
Text="Имя фильтра"
FontSize="12" FontWeight="SemiBold" Foreground="#666"
VerticalAlignment="Center"
Margin="0,0,8,0"/>
<TextBox x:Name="FilterNameBox" Grid.Column="1"
FontSize="11" FontWeight="SemiBold"
Foreground="#2D2D30"
Background="White"
BorderBrush="#CCC" BorderThickness="1"
VerticalContentAlignment="Center"
Padding="4"/>
</Grid>
<!-- TabControl -->
<TabControl x:Name="MainTabControl" Grid.Row="1">
<TabItem Header="Правила" x:Name="RulesTab">
<Grid Margin="8">
<Grid.RowDefinitions>
<RowDefinition Height="Auto"/>
<RowDefinition Height="200" MinHeight="80"/>
<RowDefinition Height="Auto"/>
<RowDefinition Height="Auto"/>
<RowDefinition Height="*"/>
</Grid.RowDefinitions>
<!-- Categories section -->
<Grid Grid.Row="0" Margin="0,0,0,4">
<Grid.ColumnDefinitions>
<ColumnDefinition Width="Auto"/>
<ColumnDefinition Width="*"/>
</Grid.ColumnDefinitions>
<TextBlock Grid.Column="0" Text="Категории"
FontSize="12" FontWeight="SemiBold" Foreground="#666"
VerticalAlignment="Center"/>
<TextBox x:Name="CategorySearch" Grid.Column="1"
FontSize="11" Margin="24,0,0,0" Height="22"
VerticalContentAlignment="Center" Padding="4,0"
Foreground="#333" Background="White"
BorderBrush="#CCC" BorderThickness="1"/>
</Grid>
<Border Grid.Row="1" BorderBrush="#CCC" BorderThickness="1"
CornerRadius="3" Padding="8" Margin="0,0,0,0"
Background="White">
<ScrollViewer VerticalScrollBarVisibility="Auto"
HorizontalScrollBarVisibility="Disabled">
<StackPanel x:Name="CategoriesPanel" Orientation="Vertical"/>
</ScrollViewer>
</Border>
<!-- GridSplitter -->
<GridSplitter Grid.Row="2" Height="5" HorizontalAlignment="Stretch"
VerticalAlignment="Center" Background="Transparent"
Cursor="SizeNS" Margin="0,2"/>
<!-- Conditions header -->
<Grid Grid.Row="3" Margin="0,0,0,6">
<Grid.ColumnDefinitions>
<ColumnDefinition Width="Auto"/>
<ColumnDefinition Width="Auto"/>
<ColumnDefinition Width="*"/>
<ColumnDefinition Width="Auto"/>
</Grid.ColumnDefinitions>
<TextBlock Grid.Column="0" Text="Условия"
FontSize="12" FontWeight="SemiBold" Foreground="#666"
VerticalAlignment="Center" Margin="0,0,15,0"/>
<StackPanel Grid.Column="1" Orientation="Horizontal" VerticalAlignment="Center">
<TextBlock Text="Логика:" Foreground="#666" FontSize="11"
VerticalAlignment="Center" Margin="0,0,6,0"/>
<RadioButton x:Name="RadioAnd" Content="И" GroupName="Logic"
IsChecked="True" Margin="0,0,10,0" FontSize="11"/>
<RadioButton x:Name="RadioOr" Content="ИЛИ" GroupName="Logic"
FontSize="11"/>
</StackPanel>
<Button x:Name="BtnAddRule" Grid.Column="3"
Content="+ Добавить условие"
Background="#5F9EA0" Foreground="White"
BorderThickness="0" Padding="10,3" FontSize="11"
Cursor="Hand"/>
</Grid>
<!-- Rules list -->
<Border Grid.Row="4" BorderBrush="#CCC" BorderThickness="1"
CornerRadius="3" Background="White" Padding="4">
<ScrollViewer VerticalScrollBarVisibility="Auto">
<StackPanel x:Name="RulesPanel"/>
</ScrollViewer>
</Border>
</Grid>
</TabItem>
<TabItem Header="Графика" x:Name="GraphicsTab">
<Border x:Name="GraphicsContent"/>
</TabItem>
</TabControl>
<!-- Warning -->
<TextBlock x:Name="WarningText" Grid.Row="2"
Foreground="#CC0000" FontSize="10" Margin="0,6,0,0"
TextWrapping="Wrap" Visibility="Collapsed"/>
<!-- Buttons -->
<StackPanel Grid.Row="3" Orientation="Horizontal"
HorizontalAlignment="Right" Margin="0,12,0,0">
<Button x:Name="BtnSave" Content="Сохранить"
Width="100" Height="28" Margin="0,0,8,0"
Background="#5F9EA0" Foreground="White"
BorderThickness="0" FontSize="12" Cursor="Hand"/>
<Button x:Name="BtnCancel" Content="Отмена"
Width="100" Height="28"
Background="#DDD" Foreground="#333"
BorderThickness="0" FontSize="12" Cursor="Hand"/>
</StackPanel>
</Grid>
</Window>
"""

RULE_ROW_XAML = """
<Grid xmlns="http://schemas.microsoft.com/winfx/2006/xaml/presentation"
xmlns:x="http://schemas.microsoft.com/winfx/2006/xaml"
Margin="2,3">
<Grid.ColumnDefinitions>
<ColumnDefinition Width="45"/>
<ColumnDefinition Width="*"/>
<ColumnDefinition Width="140"/>
<ColumnDefinition Width="250"/>
<ColumnDefinition Width="28"/>
</Grid.ColumnDefinitions>
<TextBlock x:Name="PrefixText" Grid.Column="0"
FontSize="11" FontWeight="SemiBold"
Foreground="#5F9EA0" VerticalAlignment="Center"/>
<ComboBox x:Name="ParamCombo" Grid.Column="1"
IsEditable="True"
IsTextSearchEnabled="False"
StaysOpenOnEdit="True"
IsTextSearchCaseSensitive="False"
FontSize="11" Margin="0,0,4,0" Height="24"/>
<ComboBox x:Name="OperatorCombo" Grid.Column="2"
FontSize="11" Margin="0,0,4,0" Height="24"/>
<TextBox x:Name="ValueBox" Grid.Column="3"
FontSize="11" Margin="0,0,4,0" Height="24"
VerticalContentAlignment="Center"/>
<ComboBox x:Name="ValueCombo" Grid.Column="3"
FontSize="11" Margin="0,0,4,0" Height="24"
Visibility="Collapsed"/>
<Button x:Name="BtnRemove" Grid.Column="4"
Content="x" FontSize="11"
Background="Transparent" BorderThickness="0"
Foreground="#CC0000" Cursor="Hand"
Width="24" Height="24"/>
</Grid>
"""


# =================== Editor window ===================
def show_editor(doc, filter_element, view=None):
    """Show the filter rules editor window. Pass view to enable graphics tab."""
    _bip_cache.clear()
    _unit_cache.clear()
    _yesno_pids.clear()
    _eid_choices_cache.clear()
    clear_pattern_caches()
    parsed = parse_element_filter(doc, filter_element)
    current_cat_ids = list(filter_element.GetCategories())
    current_cat_set = set(c.IntegerValue for c in current_cat_ids)
    all_cat_ids = ParameterFilterUtilities.GetAllFilterableCategories()
    all_categories = []
    for cid in all_cat_ids:
        cat = Category.GetCategory(doc, cid)
        if cat:
            is_checked = cid.IntegerValue in current_cat_set
            all_categories.append(CategoryCheckItem(cat.Name, cid, is_checked))
    all_categories.sort(key=lambda c: c.Name)
    cat_params_cache = {}
    if current_cat_ids:
        available_params = _get_params_union(doc, current_cat_ids, cat_params_cache)
    else:
        available_params = []
    is_read_only = False
    logic = "and"
    rule_items = []
    if parsed is None:
        is_read_only = True
    else:
        logic, rules_data = parsed
        for rd in rules_data:
            param_info = _find_param(
                available_params,
                rd["param_id"],
                rd["param_name"],
                spec_type_id=rd.get("spec_type_id"),
                unit_type_id=rd.get("unit_type_id"),
            )
            ri = RuleItem(
                param_info=param_info,
                value=rd["value"],
                available_params=available_params,
                param_type=rd["storage_type"],
            )
            for op in ri.AvailableOperators:
                if op.key == rd["operator_key"]:
                    ri._selected_operator = op
                    break
            rule_items.append(ri)
    window = WPFWindow(EDITOR_XAML, literal_string=True)
    window.FilterNameBox.Text = filter_element.Name

    # Graphics tab setup
    graphics_model = [None]
    if view:
        graphics_model[0] = GraphicsOverrideModel(view, filter_element.Id, doc)
        graphics_content = _init_graphics_tab(window, graphics_model[0], doc)
    else:
        window.GraphicsTab.Visibility = WinNS.Visibility.Collapsed
        graphics_content = None

    params_ref = [available_params]
    rule_rows = []
    _populate_categories(
        window, all_categories, doc, params_ref, rule_rows, cat_params_cache
    )
    if logic == "or":
        window.RadioOr.IsChecked = True
    else:
        window.RadioAnd.IsChecked = True
    for ri in rule_items:
        _add_rule_row(window, rule_rows, ri, available_params, doc, cat_params_cache)
    if not rule_items and not is_read_only:
        ri = RuleItem(available_params=available_params)
        if available_params:
            ri._selected_parameter = available_params[0]
            if ri.AvailableOperators:
                ri._selected_operator = ri.AvailableOperators[0]
        _add_rule_row(window, rule_rows, ri, available_params, doc, cat_params_cache)
    _refresh_category_availability(window, doc, rule_rows, cat_params_cache)
    if is_read_only:
        window.WarningText.Text = (
            "Этот тип фильтра не поддерживается для редактирования."
        )
        window.WarningText.Visibility = System.Windows.Visibility.Visible
        window.BtnSave.IsEnabled = False
        window.BtnAddRule.IsEnabled = False
    result = [False]

    def on_add_rule(s, e):
        ap = params_ref[0]
        ri = RuleItem(available_params=ap)
        if ap:
            ri._selected_parameter = ap[0]
            if ri.AvailableOperators:
                ri._selected_operator = ri.AvailableOperators[0]
        _add_rule_row(window, rule_rows, ri, ap, doc, cat_params_cache)

    def on_save(s, e):
        conflict = _pre_save_validate(doc, window, rule_rows, cat_params_cache)
        if conflict:
            forms.alert(conflict)
            return
        result[0] = True
        window.Close()

    def on_cancel(s, e):
        window.Close()

    def on_category_search(s, e):
        _filter_categories(window, s.Text)

    def on_logic_changed(s, e):
        _update_prefixes(window, rule_rows)

    window.BtnAddRule.Click += on_add_rule
    window.BtnSave.Click += on_save
    window.BtnCancel.Click += on_cancel
    window.CategorySearch.TextChanged += on_category_search
    window.RadioAnd.Checked += on_logic_changed
    window.RadioOr.Checked += on_logic_changed
    window.ShowDialog()
    if not result[0]:
        return False
    # Read graphics UI state before saving
    if graphics_content and graphics_model[0]:
        read_graphics_from_ui(graphics_content, graphics_model[0])
    return _save_filter(
        doc, filter_element, window, all_categories, rule_rows,
        cat_params_cache, view=view, graphics_model=graphics_model[0],
    )


def _find_param(
    available_params, param_id, fallback_name, spec_type_id=None, unit_type_id=None
):
    """Find ParameterInfo by id, or create a fallback."""
    for p in available_params:
        if p.param_id == param_id:
            return p
    return ParameterInfo(
        fallback_name, param_id, spec_type_id=spec_type_id, unit_type_id=unit_type_id
    )


def _iter_category_checkboxes(window):
    """Iterate all category CheckBox widgets from the nested group structure."""
    for group_panel in window.CategoriesPanel.Children:
        if not hasattr(group_panel, "Children"):
            continue
        for child in group_panel.Children:
            if not hasattr(child, "Children"):
                continue
            for cb in child.Children:
                tag = getattr(cb, "Tag", None)
                if tag and hasattr(tag, "CategoryId"):
                    yield cb


def _filter_categories(window, search_text):
    """Show/hide category checkboxes and letter groups based on search text."""
    query = (search_text or "").lower().strip()
    for group_panel in window.CategoriesPanel.Children:
        if not hasattr(group_panel, "Children"):
            continue
        any_visible = False
        for child in group_panel.Children:
            if not hasattr(child, "Children"):
                continue
            for cb in child.Children:
                tag = getattr(cb, "Tag", None)
                if not tag or not hasattr(tag, "Name"):
                    continue
                if not query or query in tag.Name.lower():
                    cb.Visibility = WinNS.Visibility.Visible
                    any_visible = True
                else:
                    cb.Visibility = WinNS.Visibility.Collapsed
        if query:
            group_panel.Visibility = (
                WinNS.Visibility.Visible if any_visible else WinNS.Visibility.Collapsed
            )
        else:
            group_panel.Visibility = WinNS.Visibility.Visible


def _get_cat_param_ids(doc, cat_id, cache):
    """Get parameter id set for a category (lazy cached)."""
    key = cat_id.IntegerValue
    if key not in cache:
        params = get_filterable_parameters(doc, [cat_id], lightweight=True)
        cache[key] = set(p.param_id.IntegerValue for p in params)
    return cache[key]


def _get_params_union(doc, category_ids, cache):
    """Get union of parameters across all categories."""
    seen = {}
    for cid in category_ids:
        params = get_filterable_parameters(doc, [cid], lightweight=True)
        cache[cid.IntegerValue] = set(p.param_id.IntegerValue for p in params)
        for p in params:
            pid_key = p.param_id.IntegerValue
            if pid_key not in seen:
                seen[pid_key] = p
    return sorted(seen.values(), key=lambda p: p.name)


def _populate_categories(window, categories, doc, params_ref, rule_rows, cache):
    """Add category checkboxes grouped by first letter."""
    panel = window.CategoriesPanel
    panel.Children.Clear()
    groups = {}
    for cat_item in categories:
        first_letter = cat_item.Name[0].upper() if cat_item.Name else "#"
        groups.setdefault(first_letter, []).append(cat_item)
    for letter in sorted(groups.keys()):
        group_panel = Controls.StackPanel()
        group_panel.Orientation = Controls.Orientation.Vertical
        group_panel.Margin = WinNS.Thickness(0, 2, 0, 4)
        group_panel.Tag = letter
        header = Controls.TextBlock()
        header.Text = letter
        header.FontWeight = WinNS.FontWeights.SemiBold
        header.FontSize = 12
        header.Foreground = WinNS.Media.Brushes.Gray
        header.Margin = WinNS.Thickness(0, 2, 0, 2)
        group_panel.Children.Add(header)
        separator = Controls.Separator()
        separator.Margin = WinNS.Thickness(0, 0, 0, 4)
        group_panel.Children.Add(separator)
        wrap = Controls.WrapPanel()
        wrap.Orientation = Controls.Orientation.Horizontal
        for cat_item in sorted(groups[letter], key=lambda c: c.Name):
            cb = Controls.CheckBox()
            cb.Content = cat_item.Name
            cb.IsChecked = cat_item.IsChecked
            cb.Tag = cat_item
            cb.Margin = WinNS.Thickness(0, 2, 12, 2)
            cb.FontSize = 11

            def make_handler(ci):
                def handler(s, e):
                    ci.IsChecked = s.IsChecked
                    _on_categories_changed(
                        window, categories, doc, params_ref, rule_rows, cache
                    )

                return handler

            cb.Checked += make_handler(cat_item)
            cb.Unchecked += make_handler(cat_item)
            wrap.Children.Add(cb)
        group_panel.Children.Add(wrap)
        panel.Children.Add(group_panel)


def _on_categories_changed(window, categories, doc, params_ref, rule_rows, cache):
    """Refresh available parameters (union) when categories change."""
    checked_ids = [c.CategoryId for c in categories if c.IsChecked]
    if checked_ids:
        new_params = _get_params_union(doc, checked_ids, cache)
    else:
        new_params = []
    params_ref[0] = new_params
    for ri, grid in rule_rows:
        param_combo = grid.FindName("ParamCombo")
        if not param_combo:
            continue
        old_param = param_combo.SelectedItem
        param_combo.ItemsSource = None
        param_combo.ItemsSource = list(new_params)
        param_combo.DisplayMemberPath = "name"
        if old_param:
            for p in new_params:
                if p.param_id == old_param.param_id:
                    param_combo.SelectedItem = p
                    break
        ri._available_params = new_params
    _refresh_category_availability(window, doc, rule_rows, cache)


def _refresh_category_availability(window, doc, rule_rows, cache):
    """Disable categories that lack parameters used in current rules."""
    used_pids = set()
    used_names = {}
    for ri, grid in rule_rows:
        param_combo = grid.FindName("ParamCombo")
        if not param_combo:
            continue
        p = param_combo.SelectedItem
        if not p:
            continue
        pid_int = p.param_id.IntegerValue
        used_pids.add(pid_int)
        used_names[pid_int] = p.name
    for child in _iter_category_checkboxes(window):
        tag = child.Tag
        cat_id = tag.CategoryId
        cat_pids = _get_cat_param_ids(doc, cat_id, cache)
        if not used_pids:
            child.IsEnabled = True
            child.ToolTip = None
            continue
        missing = used_pids - cat_pids
        if missing:
            names = [used_names[m] for m in missing if m in used_names]
            child.IsEnabled = False
            child.ToolTip = "Нет параметра: {}".format(", ".join(names))
        else:
            child.IsEnabled = True
            child.ToolTip = None


def _show_combo_choices(value_combo, value_box, choices, current_value):
    """Show ComboBox with choices, hide TextBox."""
    value_box.Visibility = WinNS.Visibility.Collapsed
    value_combo.Visibility = WinNS.Visibility.Visible
    value_combo.Items.Clear()
    selected_idx = -1
    for i, choice in enumerate(choices):
        value_combo.Items.Add(choice)
        if choice == current_value:
            selected_idx = i
    if selected_idx >= 0:
        value_combo.SelectedIndex = selected_idx
    elif value_combo.Items.Count > 0:
        value_combo.SelectedIndex = 0


def _show_textbox(value_combo, value_box):
    """Show TextBox, hide ComboBox."""
    value_combo.Visibility = WinNS.Visibility.Collapsed
    value_box.Visibility = WinNS.Visibility.Visible


def _setup_value_control(doc, rule_item, value_box, value_combo, category_ids):
    """Decide whether to show ComboBox or TextBox based on param type."""
    param = rule_item.SelectedParameter
    if not param:
        _show_textbox(value_combo, value_box)
        return
    spec = param.spec_type_id
    pid = param.param_id
    if _check_is_yesno(pid, spec):
        current = rule_item.Value or ""
        _show_combo_choices(value_combo, value_box, YESNO_CHOICES, current)
        return
    if param.storage_type == "element_id":
        choices = _collect_eid_choices(doc, pid, category_ids or [])
        if choices:
            names = [c[0] for c in choices]
            current = rule_item.Value or ""
            _show_combo_choices(value_combo, value_box, names, current)
            return
    _show_textbox(value_combo, value_box)


def _add_rule_row(window, rule_rows, rule_item, available_params, doc=None, cache=None):
    """Add a rule row with stable substring search using CollectionView."""
    grid = XamlReader.Load(XmlReader.Create(StringReader(RULE_ROW_XAML)))
    prefix_text = grid.FindName("PrefixText")
    param_combo = grid.FindName("ParamCombo")
    operator_combo = grid.FindName("OperatorCombo")
    value_box = grid.FindName("ValueBox")
    value_combo = grid.FindName("ValueCombo")
    btn_remove = grid.FindName("BtnRemove")
    idx = len(rule_rows)
    is_and = window.RadioAnd.IsChecked
    conjunction = "И" if is_and else "ИЛИ"
    prefix_text.Text = "ЕСЛИ" if idx == 0 else conjunction
    all_params = list(available_params)
    param_combo.ItemsSource = all_params
    param_combo.DisplayMemberPath = "name"
    param_combo.IsTextSearchEnabled = False
    view = CollectionViewSource.GetDefaultView(param_combo.ItemsSource)
    search_state = {
        "active": False,
        "query": "",
        "suppress": False,
        "last_restored": "",
    }

    def filter_func(item):
        q = search_state["query"]
        if not q:
            return True
        return q in item.name.lower()

    view.Filter = lambda item: filter_func(item)

    def _on_search_text_changed(sender, args):
        if search_state["suppress"]:
            return
        tb = sender
        typed = tb.Text or ""
        if typed == search_state.get("last_restored", ""):
            return
        caret = tb.SelectionStart
        search_state["query"] = typed.lower().strip()
        search_state["active"] = bool(search_state["query"])
        search_state["suppress"] = True
        try:
            param_combo.SelectedItem = None
            view.Refresh()
            # Restore text and caret — WPF overwrites them on SelectedItem/Refresh
            search_state["last_restored"] = typed
            tb.Text = typed
            tb.SelectionStart = caret
            tb.SelectionLength = 0
        finally:
            search_state["suppress"] = False
        if not param_combo.IsDropDownOpen:
            param_combo.IsDropDownOpen = True

    def _on_selection_changed_for_search(s, e):
        """Clear search filter when user picks an item from dropdown."""
        if search_state["suppress"]:
            return
        if not search_state["active"]:
            return
        search_state["query"] = ""
        search_state["active"] = False
        search_state["last_restored"] = ""
        search_state["suppress"] = True
        try:
            view.Refresh()
        finally:
            search_state["suppress"] = False

    param_combo.SelectionChanged += _on_selection_changed_for_search

    if rule_item.SelectedParameter:
        search_state["suppress"] = True
        param_combo.SelectedItem = rule_item.SelectedParameter
        search_state["suppress"] = False

    # Hook editable textbox — try immediately, fallback to Loaded
    param_combo.ApplyTemplate()
    _edit_tb = param_combo.Template.FindName("PART_EditableTextBox", param_combo)
    if _edit_tb:
        _edit_tb.TextChanged += _on_search_text_changed
    else:

        def _hook_search(s, e):
            param_combo.ApplyTemplate()
            tb = param_combo.Template.FindName("PART_EditableTextBox", param_combo)
            if tb:
                tb.TextChanged += _on_search_text_changed

        param_combo.Loaded += _hook_search
    operators = list(rule_item.AvailableOperators)
    operator_combo.ItemsSource = operators
    operator_combo.DisplayMemberPath = "display_name"
    if rule_item.SelectedOperator:
        operator_combo.SelectedItem = rule_item.SelectedOperator
    value_box.Text = rule_item.Value or ""

    def _get_checked_cat_ids():
        ids = []
        for cb in _iter_category_checkboxes(window):
            if cb.IsChecked:
                ids.append(cb.Tag.CategoryId)
        return ids

    # Initial value control setup
    cat_ids = _get_checked_cat_ids()
    if not rule_item.IsValueVisible:
        value_box.IsEnabled = False
        value_box.Text = ""
        value_combo.Visibility = WinNS.Visibility.Collapsed
    else:
        _setup_value_control(doc, rule_item, value_box, value_combo, cat_ids)

    def on_param_changed(s, e):
        if search_state["suppress"]:
            return
        sel = param_combo.SelectedItem
        if not sel:
            return
        rule_item.SelectedParameter = sel
        new_ops = list(rule_item.AvailableOperators)
        operator_combo.ItemsSource = new_ops
        operator_combo.DisplayMemberPath = "display_name"
        if new_ops:
            operator_combo.SelectedIndex = 0
        _setup_value_control(
            doc, rule_item, value_box, value_combo, _get_checked_cat_ids()
        )
        if cache is not None:
            _refresh_category_availability(window, doc, rule_rows, cache)

    def on_operator_changed(s, e):
        sel = operator_combo.SelectedItem
        if not sel:
            return
        rule_item.SelectedOperator = sel
        no_value = sel.key in ("has_value", "has_no_value")
        if no_value:
            value_box.Text = ""
            value_box.Visibility = WinNS.Visibility.Collapsed
            value_combo.Visibility = WinNS.Visibility.Collapsed
        else:
            _setup_value_control(
                doc, rule_item, value_box, value_combo, _get_checked_cat_ids()
            )

    def on_value_changed(s, e):
        rule_item.Value = value_box.Text

    def on_combo_changed(s, e):
        sel = value_combo.SelectedItem
        if sel is not None:
            rule_item.Value = str(sel)

    param_combo.SelectionChanged += on_param_changed
    operator_combo.SelectionChanged += on_operator_changed
    value_box.TextChanged += on_value_changed
    value_combo.SelectionChanged += on_combo_changed
    entry = (rule_item, grid)
    rule_rows.append(entry)

    def on_remove(s, e):
        if entry in rule_rows:
            rule_rows.remove(entry)
            window.RulesPanel.Children.Remove(grid)
            _update_prefixes(window, rule_rows)
            if cache is not None:
                _refresh_category_availability(window, doc, rule_rows, cache)

    btn_remove.Click += on_remove
    window.RulesPanel.Children.Add(grid)


def _update_prefixes(window, rule_rows):
    """Update ЕСЛИ/И/ИЛИ prefixes based on logic mode."""
    is_and = window.RadioAnd.IsChecked
    conjunction = "И" if is_and else "ИЛИ"
    for i, (ri, grid) in enumerate(rule_rows):
        prefix = grid.FindName("PrefixText")
        if prefix:
            prefix.Text = "ЕСЛИ" if i == 0 else conjunction


def _pre_save_validate(doc, window, rule_rows, cache):
    """Validate before saving."""
    cat_ids = []
    for child in _iter_category_checkboxes(window):
        if child.IsChecked:
            cat_ids.append(child.Tag.CategoryId)
    if not cat_ids:
        return "Не выбрана ни одна категория."
    rule_items = []
    for ri, grid in rule_rows:
        param_combo = grid.FindName("ParamCombo")
        operator_combo = grid.FindName("OperatorCombo")
        if param_combo and param_combo.SelectedItem:
            ri._selected_parameter = param_combo.SelectedItem
        if operator_combo and operator_combo.SelectedItem:
            ri._selected_operator = operator_combo.SelectedItem
        rule_items.append(ri)
    return _validate_rules_vs_categories(doc, cat_ids, rule_items, cache)


def _save_filter(
    doc, filter_element, window, all_categories, rule_rows,
    cache=None, view=None, graphics_model=None,
):
    """Save changes to the filter element and optional graphics overrides."""
    try:
        new_cat_ids = []
        for child in _iter_category_checkboxes(window):
            if child.IsChecked:
                new_cat_ids.append(child.Tag.CategoryId)
        if not new_cat_ids:
            return False
        rule_items = []
        for ri, grid in rule_rows:
            value_box = grid.FindName("ValueBox")
            value_combo = grid.FindName("ValueCombo")
            param_combo = grid.FindName("ParamCombo")
            operator_combo = grid.FindName("OperatorCombo")
            # Read value from visible control
            if value_combo and value_combo.Visibility == WinNS.Visibility.Visible:
                sel = value_combo.SelectedItem
                if sel is not None:
                    ri.Value = str(sel)
            elif value_box:
                ri.Value = value_box.Text
            if param_combo and param_combo.SelectedItem:
                ri._selected_parameter = param_combo.SelectedItem
            if operator_combo and operator_combo.SelectedItem:
                ri._selected_operator = operator_combo.SelectedItem
            rule_items.append(ri)
        is_and = window.RadioAnd.IsChecked
        new_filter = build_element_filter(rule_items, is_and, doc, new_cat_ids)
        cat_list = List[ElementId]()
        for cid in new_cat_ids:
            cat_list.Add(cid)
        # Single transaction for rules + graphics
        with Transaction(doc, "Panel_Изменить настройки фильтра") as t:
            t.Start()
            new_name = window.FilterNameBox.Text.strip()
            if new_name and new_name != filter_element.Name:
                filter_element.Name = new_name
            filter_element.SetCategories(cat_list)
            if new_filter:
                filter_element.SetElementFilter(new_filter)
            if view and graphics_model:
                ovr = build_override_settings(graphics_model)
                view.SetFilterOverrides(filter_element.Id, ovr)
            t.Commit()
        return True
    except Exception:
        print(traceback.format_exc())
        return False


def _validate_rules_vs_categories(doc, cat_ids, rule_items, cache):
    """Check that all rule parameters exist in all selected categories."""
    if not cache:
        cache = {}
    for ri in rule_items:
        if not ri.SelectedParameter:
            continue
        pid = ri.SelectedParameter.param_id.IntegerValue
        pname = ri.SelectedParameter.name
        for cid in cat_ids:
            cat_pids = _get_cat_param_ids(doc, cid, cache)
            if pid not in cat_pids:
                cat = Category.GetCategory(doc, cid)
                cat_name = cat.Name if cat else str(cid.IntegerValue)
                return 'Категория "{}" не содержит параметр "{}".'.format(
                    cat_name, pname
                )
    return None


def _init_graphics_tab(window, graphics_model, doc):
    """Load GRAPHICS_TAB_XAML into the GraphicsTab and set up controls."""
    content = XamlReader.Load(
        XmlReader.Create(StringReader(GRAPHICS_TAB_XAML))
    )
    window.GraphicsContent.Child = content
    setup_graphics_tab(content, graphics_model, doc)
    return content
