import psycopg2
import pandas as pd, numpy as np
import pandas.io.sql as sql
import urbansim.sim.simulation as sim
from utils import DataLoader

def tag(target_table_name, target_field, source_table_name, source_table_field, how='point_in_poly', target_df=None):
    """
    Tags target table with attribute of another table based on spatial relationship.

    Parameters
    ----------
    target_table_name : str
        Name of table to be tagged.  New field will be added, or existing field updated.
    target_field : str
        Name of field in target_table to add (if doesn't exist) or update (if exists).
    source_table_name : str
        Name of table containing information to tag target_table with.
    source_field : str
        Name of field in source_table that contains the information.
    how : str, optional
        How to relate the two tables spatially.  If not specified, defaults to 'point_in_poly'
    target_df : DataFrame, optional
        DataFrame to update based on the tagging operation.

    Returns
    -------
    None : None
        Field is added or updated on the target_table in the database, and returns nothing.
        Unless target_df argument is used, in which case return value is DataFrame with the
        new/updated column.

    """
    
    if srid_equality(target_table_name, source_table_name) == False:
        raise Exception('Projections are different')
        
    if db_col_exists(target_table_name, target_field) == False:
        add_integer_field(target_table_name, target_field)
        
    if how == 'point_in_poly':
        if db_col_exists(target_table_name, 'centroid') == True:
            exec_sql("update %s set %s = b.%s from %s b where st_within(%s.centroid,b.geom)" % 
                                        (target_table_name, target_field, source_table_field, source_table_name, target_table_name)) 
        else:
            exec_sql("update %s set %s = b.%s from %s b where st_within(ST_centroid(%s.geom),b.geom)" % 
                                        (target_table_name, target_field, source_table_field, source_table_name, target_table_name))
    
    if target_df:
        target_df_idx_name = target_df.index.name
        new_col = db_to_df("select %s, %s from %s" % (target_df_idx_name, target_field, target_table_name)).set_index(target_df_idx_name)[target_field]
        target_df[target_field] = new_col
        return target_df
    
def get_srid(table_name, field):
    """Returns SRID of specified table/field."""
    try:
        return db_to_df("SELECT FIND_SRID('public', '%s', '%s')" % (table_name, field)).values[0][0]
    except:
        Pass
    
def srid_equality(target_table_name, source_table_name):
    """Checks if there are multiple projections between two tables."""
    srids = []
    def check_append_srid(table_name, field_name):
        if db_col_exists(table_name, field_name):
            srids.append(get_srid(table_name,field_name))
    check_append_srid(target_table_name, 'geom')
    check_append_srid(source_table_name, 'geom')
    check_append_srid(target_table_name, 'centroid')
    check_append_srid(source_table_name, 'centroid')
    srids = np.unique(srids)
    return False if len(srids[srids>0]) > 1 else True  
    
def db_col_exists(table_name, column_name):
    """Tests if column on database table exists"""
    test = db_to_df("SELECT column_name FROM information_schema.columns WHERE table_name='%s' and column_name='%s';"%(table_name,column_name))
    return True if len(test) > 0 else False

def add_integer_field(table_name, field_to_add):
    """Add integer field to table."""
    exec_sql("alter table %s add %s integer default 0;" % (table_name, field_to_add))

def exec_sql(query):
    """Executes SQL query."""
    cur = sim.get_injectable('cur')
    conn = sim.get_injectable('conn')
    cur.execute(query)
    conn.commit()
    
def db_to_df(query):
    """Executes SQL query and returns DataFrame."""
    conn = sim.get_injectable('conn')
    return sql.read_frame(query, conn)
    
def reproject(target_table, geometry_column='geom', config_dir, new_table=None):
    """
    Reprojects target table into the srid specified in the project config

    Parameters
    ----------
    target_table: str
        Name of table to reproject.  Default is in-place reprojection.
    geometry_column : str
        Name of the geometry column in the target table. Default is 'geom'.
    config_dir : str
        Path to the directory where the project config is stored.
    source_field : str
        Name of field in source_table that contains the information.
    new_table: str, optional
        If new_table is specified, a copy of target table is made with name new_table
    
    Returns
    -------
    None : None
        Target table's geometry column is reprojected to the SRID found in the config file.
        Function detects current target table SRID and project SRID and converts on the database.

    """
    project_srid = str(DataLoader(config_dir).srid)
    table_srid = str(st.get_srid(target_table, geometry_column))
    if new_table:
        st.exec_sql("CREATE TABLE %s as SELECT * FROM %s" % (new_table, target_table))
        st.exec_sql("SELECT UpdateGeometrySRID('%s', '%s', %s)" % (new_table, geometry_column, project_srid))
        st.exec_sql("UPDATE %s SET %s = ST_TRANSFORM(ST_SetSRID(%s, %s), %s)" % (new_table, geometry_column, geometry_column, table_srid, project_srid))
    else:
        st.exec_sql("SELECT UpdateGeometrySRID('%s', '%s', %s)" % (target_table, geometry_column, project_srid))
        st.exec_sql("UPDATE %s SET %s = ST_TRANSFORM(ST_SetSRID(%s, %s), %s)" % (target_table, geometry_column, geometry_column, table_srid, project_srid))