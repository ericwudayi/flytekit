import typing
from collections import OrderedDict

import pandas as pd
import pytest
from pandas.testing import assert_frame_equal
from typing_extensions import Annotated  # type: ignore

import flytekit.configuration
from flytekit import FlyteContextManager, StructuredDataset, kwtypes
from flytekit.configuration import Image, ImageConfig
from flytekit.core import context_manager
from flytekit.core.condition import conditional
from flytekit.core.task import task
from flytekit.core.workflow import WorkflowFailurePolicy, WorkflowMetadata, WorkflowMetadataDefaults, workflow
from flytekit.exceptions.user import FlyteValidationException, FlyteValueException
from flytekit.tools.translator import get_serializable
from flytekit.types.schema import FlyteSchema

import io
import sys

default_img = Image(name="default", fqn="test", tag="tag")
serialization_settings = flytekit.configuration.SerializationSettings(
    project="project",
    domain="domain",
    version="version",
    env=None,
    image_config=ImageConfig(default_image=default_img, images=[default_img]),
)

def test_rshift_task_workflow():
    @task
    def task_a():
        print("a")

    @task
    def task_b():
        print("b")
    
    @task
    def task_c():
        print("c")
    
    @workflow(simulate_remote=True)
    def my_wf():
        a = task_a()
        b = task_b()
        c = task_c()


        c >> b >> a 
    capturedOutput = io.StringIO()          
    sys.stdout = capturedOutput
    my_wf()                            
    sys.stdout = sys.__stdout__                  
    assert capturedOutput.getvalue() == "c\nb\na\n"

def test_rshift_task_subworkflow():
    @task
    def task_a():
        print("a")

    @task
    def task_b():
        print("b")
    
    @task
    def task_c():
        print("c")
    
    @workflow
    def sub_wf():
        t2 = task_b()
        t3 = task_c()

        t3 >> t2

    @workflow(simulate_remote=True)
    def my_wf():
        sf = sub_wf()
        t3 = task_a()
        t2 = task_b()
        t1 = task_c()

        t1 >> t2 >> t3 >> sf
    capturedOutput = io.StringIO()          
    sys.stdout = capturedOutput
    my_wf()                            
    sys.stdout = sys.__stdout__                  
    assert capturedOutput.getvalue() == "c\nb\na\nc\nb\n"


def test_rshift_task_pass_type():
    @task
    def task_five() -> int:
        print("5")
        return 5
    
    @task
    def task_six() -> int:
        print("6")
        return 6

    @task
    def task_add(a : int, b : int) -> int:
        print(a+b)
        return a + b
    
    @workflow(simulate_remote=True)
    def my_wf() -> int:
        five = task_five()
        six = task_six()
        add = task_add(a=five, b=six)
        six >> five >> add
        return add
    capturedOutput = io.StringIO()          
    sys.stdout = capturedOutput
    result = my_wf()                            
    sys.stdout = sys.__stdout__                  
    assert capturedOutput.getvalue() == "6\n5\n11\n"
    assert result == 11


def test_wf_nested_comp():
    @task
    def t1(a: int) -> int:
        print ("t1", a)
        a = a + 5
        return a

    @workflow(simulate_remote=True)
    def outer() -> typing.Tuple[int, int]:
        # You should not do this. This is just here for testing.
        @workflow
        def wf2() -> int:
            print ("wf2")
            return t1(a=5)

        ft = t1(a=3)
        fwf = wf2()
        fwf >> ft
        return ft, fwf

    capturedOutput = io.StringIO()          
    sys.stdout = capturedOutput
    _ = outer()                            
    sys.stdout = sys.__stdout__                  
    assert capturedOutput.getvalue() == "wf2\nt1 5\nt1 3\n"

    assert (8, 10) == outer()
    entity_mapping = OrderedDict()

    model_wf = get_serializable(entity_mapping, serialization_settings, outer)

    assert len(model_wf.template.interface.outputs) == 2
    assert len(model_wf.template.nodes) == 2
    assert model_wf.template.nodes[1].workflow_node is not None

    sub_wf = model_wf.sub_workflows[0]
    assert len(sub_wf.nodes) == 1
    assert sub_wf.nodes[0].id == "n0"
    assert sub_wf.nodes[0].task_node.reference_id.name == "tests.flytekit.unit.core.test_workflows_simulate_remote.t1"





def test_condition_simulate_remote():
    @task
    def square(n: float) -> float:
        print ("square")
        return n * n


    @task
    def double(n: float) -> float:
        print ("double")
        return 2 * n

    @workflow(simulate_remote=True)
    def multiplier_3(my_input: float):
        
        a = (conditional("fractions")
            .if_((my_input >= 0) & (my_input < 1.0))
            .then(double(n=my_input))
            .else_()
            .then(square(n=my_input))
            
        )
        b = (conditional("fractions2")
            .if_((my_input >= 0) & (my_input < 1.0))
            .then(square(n=my_input))
            .else_()
            .then(double(n=my_input))
        )

        b >> a

        ## This line have a bug, but not cause by simulate_remote
        #print (b, a)
        #return a + b
    capturedOutput = io.StringIO()          
    sys.stdout = capturedOutput
    result = multiplier_3(my_input=0.5)                            
    sys.stdout = sys.__stdout__                  
    assert capturedOutput.getvalue() == "square\ndouble\n"
    #assert result == 1.25                     
    
