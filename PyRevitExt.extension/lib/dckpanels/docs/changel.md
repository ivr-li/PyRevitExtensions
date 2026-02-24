 YesNo detection:
  - _is_yesno_spec() — проверяет ForgeTypeId spec через .TypeId строку (содержит "yesno"/"boolean")
  - _check_is_yesno() — единая функция: для shared параметров через spec, для BIP через кэш _yesno_pids
  - _yesno_pids — кэш заполняется в _build_unit_cache_for_category через Definition.GetDataType() на sample элементе
  - _cache_yesno_param() — проверяет Integer параметр и добавляет в _yesno_pids

  ElementId dropdown:
  - _collect_eid_choices() — точка входа с кэшем _eid_choices_cache
  - _collect_eid_by_class_detection() — определяет класс элемента (.NET Type) по реальному значению параметра
  - _find_sample_eid_value() — 3-уровневый поиск: get_Parameter(bip) → скан категории → скан всего документа
  - _collect_elements_of_class() — собирает все элементы найденного класса

  UI:
  - ValueCombo в XAML — ComboBox рядом с TextBox
  - _setup_value_control() — переключает TextBox/ComboBox по storage_type
  - _show_combo_choices() / _show_textbox() — управление видимостью
  - YESNO_CHOICES — ["Да", "Нет"] для boolean параметров
