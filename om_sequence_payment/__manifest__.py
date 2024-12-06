{
    'name': "AIU | OM Sequence",
    'summary': "Unique sequence management for account.move and account.payment tailored for OMEGA MAS.",
    'description': """
        This module introduces a systematic sequence management system for account.move 
        and account.payment entities specifically designed for OMEGA MAS. It enhances 
        the existing accounting module by ensuring that all financial transactions are assigned 
        distinct sequence numbers, improving traceability and organization within financial records.
    """,
    'author': "Bayu Indra Kusuma",
    'website': "https://bayuik.dev",
    'category': 'AIU Module',
    'application': True,
    'version': '0.1',
    'depends': ['account'],
    'license': 'OPL-1',
    'data': [
        'data/ir_sequence_data.xml',
        'data/ir_sequence_data2.xml',
    ],
}
