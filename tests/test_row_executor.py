from __future__ import annotations

from pathlib import Path

from datamapx.config import load_config
from datamapx.runner import run_load_phase
from datamapx.transform.row_executor import build_rowwise_output, prepare_rowwise_inputs
from datamapx.validation import validate_input_rows

FIXTURES = Path(__file__).parent / "fixtures" / "mapping"


def test_row_executor_preserves_successful_rows_on_lookup_stop() -> None:
    config = load_config(FIXTURES / "mapping_config_lookup_missing_error.yml")
    config = config.model_copy(
        update={
            "error_handling": config.error_handling.model_copy(
                update={"on_lookup_missing": "stop"}
            )
        }
    )

    load_result = run_load_phase(config, FIXTURES)
    input_name = next(iter(config.inputs))
    output_name = next(iter(config.outputs))
    input_validation_result = validate_input_rows(
        config,
        load_result.input_df,
        input_name,
        load_result.reference_dfs,
    )

    result = build_rowwise_output(
        config=config,
        input_df=input_validation_result.dataframe,
        input_name=input_name,
        output_columns=list(config.outputs[output_name].columns),
        reference_dfs=load_result.reference_dfs,
        base_error_count=len(input_validation_result.error_rows),
    )

    assert result.stop_info is not None
    assert result.stop_info.reason == "lookup_missing"
    assert result.output_df["id"].tolist() == ["u001", "u002"]


def test_row_executor_reports_transform_errors_as_row_errors() -> None:
    config = load_config(FIXTURES / "mapping_config_expression_missing_value.yml")
    load_result = run_load_phase(config, FIXTURES)
    input_name = next(iter(config.inputs))
    output_name = next(iter(config.outputs))
    input_validation_result = validate_input_rows(
        config,
        load_result.input_df,
        input_name,
        load_result.reference_dfs,
    )

    result = build_rowwise_output(
        config=config,
        input_df=input_validation_result.dataframe,
        input_name=input_name,
        output_columns=list(config.outputs[output_name].columns),
        reference_dfs=load_result.reference_dfs,
        base_error_count=len(input_validation_result.error_rows),
    )

    assert result.stop_info is None
    assert result.mapping_error_rows[0].rule == "transform_error"


def test_row_preparation_uses_one_batch_when_rows_have_no_mapping_errors() -> None:
    config = load_config(FIXTURES / "mapping_config_lookup.yml")
    load_result = run_load_phase(config, FIXTURES)
    input_name = next(iter(config.inputs))
    input_validation_result = validate_input_rows(
        config,
        load_result.input_df,
        input_name,
        load_result.reference_dfs,
    )

    result = prepare_rowwise_inputs(
        config=config,
        input_df=input_validation_result.dataframe,
        input_name=input_name,
        reference_dfs=load_result.reference_dfs,
        base_error_count=0,
    )

    assert len(result.prepared_rows) == 1
    assert len(result.prepared_rows[0].input_df) == result.input_rows_after_filter
