"""
计算器工具模块

文件功能：
    定义calculator Tool，提供安全的数学表达式计算能力。
    作为LangGraph Tool注册，由LLM通过Tool Calling自主调用。

在系统架构中的定位：
    位于Agent工具层，为Agent提供精确数值计算能力。
    解决LLM数学计算不可靠的问题（尤其是百分比、比率、环比等运算）。

主要使用场景：
    - 用户问"在线率是多少"时，LLM调用此工具计算 在线数/总数*100
    - 用户问"告警环比增长了多少"时，LLM调用此工具计算 (本月-上月)/上月*100
    - 任何需要精确数值运算的场景，避免LLM心算出错

核心函数：
    - calculator: LangGraph Tool，接收数学表达式，返回计算结果
    - _safe_eval: 安全表达式解析器，基于AST白名单机制

专有技术说明：
    - 使用Python ast模块解析表达式为AST树，递归求值
    - 白名单机制：仅允许数字常量、算术运算符(+,-,*,/,//,%,**)和6个内置函数(round/abs/min/max/int/float)
    - 禁止任意代码执行：不支持变量赋值、函数定义、模块导入、属性访问等
    - 浮点数智能精度处理：极小值归零、大数保留2位、中间值保留6位或2位

安全注意事项：
    - 绝不使用eval()或exec()，所有表达式通过AST白名单校验
    - 不支持的AST节点类型直接抛出ValueError
    - 除零错误单独捕获，返回友好错误信息

关联文件：
    - agent_backend/agent/tools/__init__.py: ALL_TOOLS注册
    - agent_backend/agent/prompts.py: SYSTEM_PROMPT中计算工具决策规则
    - agent_backend/agent/nodes.py: tool_result_node收集calculator_results
"""
from __future__ import annotations

import ast
import json
import logging
import operator
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

_SAFE_OPERATORS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
    ast.USub: operator.neg,
    ast.UAdd: operator.pos,
}

_SAFE_FUNCTIONS = {
    "round": round,
    "abs": abs,
    "min": min,
    "max": max,
    "int": int,
    "float": float,
}


class CalculatorInput(BaseModel):
    """计算器工具入参模型"""
    expression: str = Field(description="数学表达式，如 '156/890*100' 或 'round((234-189)/189*100, 2)'")


def _safe_eval(node: ast.AST) -> Any:
    """
    安全的AST表达式求值器。

    递归遍历AST节点，仅允许白名单内的运算符和函数。
    遇到不在白名单内的节点类型时抛出ValueError。

    参数：
        node: AST节点

    返回：
        Any: 求值结果（int或float）

    异常：
        ValueError: 遇到不支持的运算符、函数或表达式类型

    安全机制：
        - 仅支持Constant(UnaryOp/BinOp/Call三种AST节点
        - 运算符白名单: +, -, *, /, //, %, **, 一元负号, 一元正号
        - 函数白名单: round, abs, min, max, int, float
        - 禁止属性访问(ast.Attribute)、下标访问(ast.Subscript)等
    """
    if isinstance(node, ast.Constant):
        if isinstance(node.value, (int, float)):
            return node.value
        raise ValueError(f"不支持的常量类型: {type(node.value).__name__}")

    if isinstance(node, ast.UnaryOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"不支持的运算符: {op_type.__name__}")
        operand = _safe_eval(node.operand)
        return _SAFE_OPERATORS[op_type](operand)

    if isinstance(node, ast.BinOp):
        op_type = type(node.op)
        if op_type not in _SAFE_OPERATORS:
            raise ValueError(f"不支持的运算符: {op_type.__name__}")
        left = _safe_eval(node.left)
        right = _safe_eval(node.right)
        return _SAFE_OPERATORS[op_type](left, right)

    if isinstance(node, ast.Call):
        if not isinstance(node.func, ast.Name):
            raise ValueError("不支持的表达式: 仅允许调用内置函数(round/abs/min/max/int/float)")
        func_name = node.func.id
        if func_name not in _SAFE_FUNCTIONS:
            raise ValueError(f"不支持的函数: {func_name}，可用函数: {', '.join(_SAFE_FUNCTIONS.keys())}")
        args = [_safe_eval(arg) for arg in node.args]
        return _SAFE_FUNCTIONS[func_name](*args)

    raise ValueError(f"不支持的表达式类型: {type(node).__name__}")


@tool(args_schema=CalculatorInput)
def calculator(expression: str) -> str:
    """
    执行数学计算。
    当需要计算百分比、比率、差值、环比、同比等数值运算时使用此工具。
    支持基本算术运算(+、-、*、/、//、%、**)和函数(round、abs、min、max、int、float)。

    参数：
        expression: 数学表达式，如 '156/890*100' 或 'round((234-189)/189*100, 2)'

    返回：
        str: JSON格式字符串，包含expression和result字段；
             计算失败时包含expression和error字段
    """
    logger.info(f"\n[calculator] 计算表达式: {expression}")

    try:
        tree = ast.parse(expression, mode="eval")
        result = _safe_eval(tree.body)

        if isinstance(result, float):
            if abs(result) < 1e-10:
                result = 0.0
            elif abs(result) >= 1e6:
                result = round(result, 2)
            else:
                rounded_6 = round(result, 6)
                rounded_2 = round(result, 2)
                result = rounded_2 if round(rounded_6 - rounded_2, 8) == 0 else rounded_6

        logger.info(f"\n[calculator] 计算结果: {expression} = {result}")
        return json.dumps({
            "expression": expression,
            "result": result,
        }, ensure_ascii=False)

    except ZeroDivisionError:
        logger.warning(f"\n[calculator] 除零错误: {expression}")
        return json.dumps({
            "expression": expression,
            "error": "除零错误：表达式中存在除以零的运算",
        }, ensure_ascii=False)
    except ValueError as e:
        logger.warning(f"\n[calculator] 表达式错误: {e}")
        return json.dumps({
            "expression": expression,
            "error": str(e),
        }, ensure_ascii=False)
    except Exception as e:
        logger.error(f"[calculator] 异常: {type(e).__name__}: {e}")
        return json.dumps({
            "expression": expression,
            "error": f"计算失败: {type(e).__name__}: {e}",
        }, ensure_ascii=False)
