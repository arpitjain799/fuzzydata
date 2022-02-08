import itertools
import os
import string
from collections import defaultdict

import pandas
import numpy as np
import logging

from functools import partial
from typing import Callable, Dict
from faker import Faker
from itertools import chain


logging.getLogger('faker').setLevel(logging.ERROR)
logger = logging.getLogger(__name__)


_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_UNIQUE_DICTIONARY = string.ascii_letters+string.digits


def load_function_dict(directory=_THIS_DIR+'/config/'):
    return {
        'joinable': [line.rstrip('\n') for line in open(directory + 'joinable_cols.txt')],
        'groupable': [line.rstrip('\n') for line in open(directory + 'groupable_cols.txt')],
        'numeric': [line.rstrip('\n') for line in open(directory + 'numeric_cols.txt')],
        'string': [line.rstrip('\n') for line in open(directory + 'string_cols.txt')],
    }


def generate_inverse_function_dict(function_dict):
    inv_functions = defaultdict(list)
    for k, vs in function_dict.items():
        for v in vs:
            inv_functions[v].append(k)
    return inv_functions


_gen_functions = load_function_dict()
logger.debug(_gen_functions)
_faker_cols = list(set(chain(*_gen_functions.values())))
_inv_gen_functions = generate_inverse_function_dict(_gen_functions)


def generate_prefix(symbol_dict: str, size: int=5) -> str:
    return ''.join(np.random.choice(list(symbol_dict), size))


def generate_table(num_rows: int=100, column_dict: Dict=None, pd=pandas) -> pandas.DataFrame:
    faker = Faker()
    logger.info(f'Generating base df with {num_rows} rows and {len(column_dict.keys())} columns')
    logger.debug(f'Column list: {column_dict.keys()}')
    series_list = []
    label_list = []
    for label, column in column_dict.items():
        series_list.append(pd.Series((faker.format(column) for _ in range(num_rows))))
        label_list.append(label)
    return pd.concat(series_list, axis=1, keys=label_list)


def generate_schema(num_cols: int, unique_prefix: Callable = partial(generate_prefix, _UNIQUE_DICTIONARY, size=5)) -> Dict[str, str]:
    column_dict = {}
    num_col_types = len(_gen_functions.keys())
    if num_cols < num_col_types:
        random_selection = np.random.choice(_faker_cols, size=num_cols)
    else:
        # Better randomization of columns to ensure at least one of each type are generated
        random_selection = []
        num_array = np.ones(num_col_types, dtype=int)
        while sum(num_array) < num_cols:
            ix = np.random.randint(0, 4)
            num_array[ix] += 1
        for ix, col_type in enumerate(_gen_functions.keys()):
            random_selection.extend(np.random.choice(_gen_functions[col_type], size=num_array[ix]))

    logger.debug(random_selection)
    column_dict.update({f'{unique_prefix()}__{r}': r for r in random_selection})
    logger.debug(f'Selected columns for this schema: {column_dict.values()}')
    return column_dict


def get_schema_type_mapping(column_dict):
    # Do not need inverse schema maps yet...
    schema_type_mapping = defaultdict(list)
    for col, faker_type in column_dict.items():
        for col_type in _inv_gen_functions[faker_type]:
            schema_type_mapping[col_type].append(col)

    logger.debug(f'Inverse ColumnType Mapping: {schema_type_mapping}')

    return schema_type_mapping


def select_rand_cols(df_col_types, num, col_type=None):
    if not col_type:
        all_options = list(itertools.chain(df_col_types.values()))
    else:
        all_options = df_col_types[col_type]
    try:
        logger.debug(f'Selection Options for {col_type} type: {all_options}')
        options = np.random.choice(all_options, num, replace=False).tolist()
    except ValueError as e:
        logger.warning(f'Could not select {num} columns of type {col_type}')
        return None
    return options


def select_rand_aggregate():
    return np.random.choice(['min', 'max', 'sum', 'mean', 'count'], 1)[0]


def get_rand_percentage(minimum=0.1, maximum=0.99):
    return round((maximum - minimum) * np.random.random_sample() + minimum,  2)


def generate_ops_choices(schema: Dict[str, str], num_rows: int) -> Dict[str, Dict]:
    """
    Generate the a number of options for the next operation to be performed on a given table with schema and num_rows
    :param schema: Column Map
    :param num_rows: number of rows in the table
    :return: Dict of ops: args choices
    """
    # Generates parameters for each op as well.

    ops_choices = []
    df_col_types = get_schema_type_mapping(schema)

    logger.debug(f"df_col_types: {df_col_types}")
    '''
    OPS REQUIREMENTS
    assign_numeric = one numeric col, random scalar value
    assign_string = one string col
    groupby = one groupable col, at least one numeric col, random aggregation function
    iloc = two numbers, minimum 10 rows
    sample = random DF fraction
    point_edit = any column. old value, new value
    dropcol = any column
    merge = atleast one joinable column. new dataframe with that joinable column and its values. 
    pivot = one index column, one groupable column and one numeric values column.
    '''

    if 'numeric' in df_col_types:
        # # assign_numeric option
        numeric_col = select_rand_cols(df_col_types, 1, 'numeric')[0]
        # random_scalar = np.random.randint(1, 100, 2)
        # new_col_name = f"{numeric_col}__{str(random_scalar[0])}x + {str(random_scalar[1])}"
        # ops_choices.append((assign_numeric,
        #                     {'numeric_col': numeric_col,
        #                      'random_scalar': random_scalar,
        #                      'new_col_name': new_col_name}
        #                     ))

        if 'groupable' in df_col_types:
            # groupby, pivots now possible
            num_groups = min(np.random.randint(1, 3), len(df_col_types['groupable']))
            group_cols = select_rand_cols(df_col_types, num_groups, 'groupable')
            func = select_rand_aggregate()
            ops_choices.append({'op': 'groupby',
                                'args': {'group_columns': group_cols,
                                         'agg_columns': df_col_types['numeric'],
                                         'agg_function': func}
                                })

            # pivot selections
            if len(df_col_types['groupable']) >= 2:
                index, columns = select_rand_cols(df_col_types, 2, 'groupable')
                values = numeric_col
                ops_choices.append({'op': 'pivot',
                                    'args': {'index_cols': [index], 'columns': [columns], 'value_col': [values],
                                             'agg_func': select_rand_aggregate()}
                                    })

    if 'joinable' in df_col_types:
        on = select_rand_cols(df_col_types, 1, 'joinable')[0]
        # TODO: Do not allow joins yet
        # ops_choices.append(('merge', {'on': on}))

    # if 'string' i df_col_types:
    #     #     col = select_rand_cols(df_columns, 1, 'string')[0]
    #     #     new_col_name = col + '__swapcase'
    #     #     ops_choices.append((assign_string, {'col': col, 'new_col_name': new_col_name}))
    #
    #     # Remaining operations are possible if df has at least 10 rows
    #
    if num_rows >= 10:
        frac = get_rand_percentage()
        ops_choices.append({'op': 'sample', 'args': {'frac': frac}})
    #
    #         # # point edits
    #         # col = select_rand_cols(df_columns, 1)[0]
    #         # colvalues = set(df_dict[df_name][col].values)
    #         # old_value = np.random.choice(list(colvalues), 1)[0]
    #         # if col in self.column_mapping:
    #         #     faker_col = self.column_mapping[col]
    #         #     new_value = self.faker.format(faker_col)
    #         #     ops_choices.append((point_edit, {'col': col, 'old_value': old_value, 'new_value': new_value}))
    #
    #     # Dropcol only if dataframe has at least 2 columns
    #     if len(df_columns) >= 2:
    #         col = select_rand_cols(df_columns, 1)[0]
    #         ops_choices.append(('dropcol', {'col': col}))
    #
    return ops_choices


def generate_workflow(workflow_class, name='wf', num_versions=10, base_shape=(10, 1000),
                      out_directory='/tmp/dataset', bfactor=1.0):

    wf = workflow_class(name=name, out_directory=out_directory)
    wf.generate_base_artifact(num_cols=base_shape[0], num_rows=base_shape[1])

    num_generated = len(wf.artifact_list)

    while num_generated < num_versions:
        try:
            source_artifact = wf.select_random_artifact(bfactor=bfactor)
            if not source_artifact.schema_map:
                continue
            ops_choices = generate_ops_choices(schema=source_artifact.schema_map,
                                               num_rows=source_artifact.num_rows())

            if ops_choices:
                logger.debug(f'Ops Choices: {ops_choices}')
                selected_op = np.random.choice(ops_choices, 1)[0]
                # TODO: Handle Merge Op here
                logger.info(f"Executing Operation: {source_artifact.label} "
                            f"=={selected_op['op']}==> artifact_{num_generated}")
                wf.generate_artifact_from_operation([source_artifact], **selected_op)

                # TODO: Exception Handling for empty datagframes generated
                # if not next_df:
                #    logger.warning('Could not apply_op, retrying...')
            else:
                logger.warning(f"No ops choices available for {source_artifact.label}")
                break

            num_generated = len(wf.artifact_list)
        except NotImplementedError as e:
            logger.warning(f'Attempting an operation that is not implemented for this workflow type:'
                           f" {selected_op['op']}")
        except Exception as e:
            logger.error('Error during generation, stopping...')
            logger.error(f'Writing out all files to {wf.out_dir}')
            wf.serialize_workflow()
            raise e

        # TODO Additional Exception Handling
        '''
        except pd.errors.EmptyDataError as e:
            print("Empty DF result")
            retries -= 1
            pass
        except ColumnTypeException as e:
            print(e)
            print("Cannot apply operation because of missing column type, skipping")
            retries -= 1
            pass
        except TooSimilarException as e:
            print(e)
            print("Cannot apply operation because generated dataframe is too similar to ones already generated, skipping")
            retries -= 1
            pass
        except Exception as e:
            dataset.lastargs = {}
            print(dataset.lastmatchoice)
            tb = traceback.format_exc()
            errors.append({choice: tb})
            print(dataset.lastargs)
            raise

        if retries == 0:
            dataset.opcount = 0
            dataset.currentdf = None
            chain_retries -= 1
        '''

    wf.serialize_workflow()

    return wf
