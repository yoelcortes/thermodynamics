# -*- coding: utf-8 -*-
"""
Created on Tue Nov 26 02:34:56 2019

@author: yoelr
"""
import numpy as np
from . import material_indexer as index 
from . import equilibrium as eq
from . import functional as fn
from .base import units_of_measure as thermo_units
from .base.display_units import DisplayUnits
from .exceptions import DimensionError
from .settings import settings
from .thermal_condition import ThermalCondition
from .registry import registered
from .utils import Cache, assert_same_chemicals
from . import pipping

__all__ = ('Stream', )


# %% Utilities

mol_units = index.ChemicalMolarFlowIndexer.units
mass_units = index.ChemicalMassFlowIndexer.units
vol_units = index.ChemicalVolumetricFlowIndexer.units

# %%
@registered(ticket_name='s')
class Stream:
    __slots__ = ('_ID', '_imol', '_TP', '_thermo', '_streams', '_vle', '_sink', '_source', 'price')
    
    #: [DisplayUnits] Units of measure for IPython display (class attribute)
    display_units = DisplayUnits(T='K', P='Pa',
                                 flow=('kmol/hr', 'kg/hr', 'm3/hr'),
                                 N=5)

    _index_cache = {}

    def __init__(self, ID='', flow=(), phase='l', T=298.15, P=101325., units=None,
                 price=0., thermo=None, **chemical_flows):
        self._TP = ThermalCondition(T, P)
        self._thermo = thermo = thermo or settings.get_thermo(thermo)
        self._load_indexer(flow, phase, thermo.chemicals, chemical_flows)
        self.price = price
        if units:
            indexer, factor = self._get_indexer_and_factor(units)
            indexer[...] = self.mol * factor
        self._sink = self._source = None
        self._register(ID)
    
    def _load_indexer(self, flow, phase, chemicals, chemical_flows):
        """Initialize molar flow rates."""
        if flow is ():
            if chemical_flows:
                imol = index.ChemicalMolarFlowIndexer(phase, chemicals=chemicals, **chemical_flows)
            else:
                imol = index.ChemicalMolarFlowIndexer.blank(phase, chemicals)
        else:
            assert not chemical_flows, ("may specify either 'flow' or "
                                        "'chemical_flows', but not both")
            if isinstance(flow, index.ChemicalMolarFlowIndexer):
                imol = flow 
                imol.phase = phase
            else:
                imol = index.ChemicalMolarFlowIndexer.from_data(flow, phase, chemicals)
        self._imol = imol

    def _get_indexer_and_factor(self, units):
        cache = self._index_cache
        if units in cache:
            name, factor = cache[units]
        else:
            dimensionality = thermo_units.get_dimensionality(units)
            if dimensionality == mol_units.dimensionality:
                name = 'imol'
                factor = mol_units.conversion_factor(units)
            elif dimensionality == mass_units.dimensionality:
                name = 'imass'
                factor = mass_units.conversion_factor(units)
            elif dimensionality == vol_units.dimensionality:
                name = 'ivol'
                factor = vol_units.conversion_factor(units)
            else:
                raise DimensionError(f"dimensions for flow units must be in molar, "
                                     f"mass or volumetric flow rates, not '{dimensionality}'")
            cache[units] = name, factor
        return getattr(self, name), factor

    ### Pipping ###
    
    @property
    def sink(self):
        return self._sink
    @property
    def source(self):
        return self._source
    
    # Forward pipping
    def __sub__(self, index):
        if isinstance(index, int):
            return pipping.Sink(self, index)
        elif isinstance(index, Stream):
            raise TypeError("unsupported operand type(s) for -: "
                            f"'{type(self)}' and '{type(index)}'")
        return index.__rsub__(self)

    def __rsub__(self, index):
        if isinstance(index, int):
            return pipping.Source(self, index)
        elif isinstance(index, Stream):
            raise TypeError("unsupported operand type(s) for -: "
                            "'{type(self)}' and '{type(index)}'")
        return index.__sub__(self)

    # Backward pipping    
    __pow__ = __sub__
    __rpow__ = __rsub__
    

    ### Property getters ###

    def get_flow(self, units, IDs=...):
        indexer, factor = self._get_indexer_and_factor(units)
        return factor * indexer[IDs]
    
    def set_flow(self, data, units, IDs=...):
        indexer, factor = self._get_indexer_and_factor(units)
        indexer[IDs] = np.asarray(data, dtype=float) / factor
    
    def get_property(self, name, units):
        units_dct = thermo_units.stream_units_of_measure
        if name in units_dct:
            original_units = units_dct[name]
        else:
            raise ValueError(f"no property with name '{name}'")
        value = getattr(self, name)
        factor = original_units.conversion_factor(units)
        return value * factor
    
    def set_property(self, name, value, units):
        units_dct = thermo_units.stream_units_of_measure
        if name in units_dct:
            original_units = units_dct[name]
        else:
            raise ValueError(f"no property with name '{name}'")
        factor = original_units.conversion_factor(units)
        setattr(self, name, value / factor)
    
    ### Stream data ###
    
    @property
    def thermo(self):
        return self._thermo
    @property
    def chemicals(self):
        return self._thermo.chemicals
    @property
    def mixture(self):
        return self._thermo.mixture

    @property
    def thermal_condition(self):
        return self._TP

    @property
    def T(self):
        return self._TP.T
    @T.setter
    def T(self, T):
        self._TP.T = T
    
    @property
    def P(self):
        return self._TP.P
    @P.setter
    def P(self, P):
        self._TP.P = P
    
    @property
    def phase(self):
        return self._imol._phase.phase
    @phase.setter
    def phase(self, phase):
        self._imol._phase.phase = phase
    
    @property
    def mol(self):
        return self._imol._data
    @mol.setter
    def mol(self, value):
        mol = self.mol
        if mol is not value:
            mol[:] = value
    
    @property
    def mass(self):
        return self.imass._data
    @mass.setter
    def mass(self, value):
        mass = self.mass
        if mass is not value:
            mass[:] = value
    
    @property
    def vol(self):
        return self.ivol._data
    @vol.setter
    def vol(self, value):
        vol = self.vol
        if vol is not value:
            vol[:] = value
        
    @property
    def imol(self):
        return self._imol
    @property
    def imass(self):
        return self._imol.by_mass()
    @property
    def ivol(self):
        return self._imol.by_volume(self._TP)
    
    ### Net flow properties ###
    
    @property
    def cost(self):
        return self.price * self.F_mass
    
    @property
    def F_mol(self):
        return self.mol.sum()
    @F_mol.setter
    def F_mol(self, value):
        self.mol[:] *= value/self.F_mol
    @property
    def F_mass(self):
        return (self.chemicals.MW * self.mol).sum()
    @F_mass.setter
    def F_mass(self, value):
        self.mol[:] *= value/self.F_mass
    @property
    def F_vol(self):
        return self.mixture.V_at_TP(self.phase, self.mol, self._TP)
    @F_vol.setter
    def F_vol(self, value):
        self.vol[:] *= value/self.F_vol
    
    @property
    def H(self):
        return self.mixture.H_at_TP(self.phase, self.mol, self._TP)
    @H.setter
    def H(self, H):
        self.T = self.mixture.solve_T(self.phase, self.mol, H, self.T, self.P)

    @property
    def S(self):
        return self.mixture.S_at_TP(self.phase, self.mol, self._TP)
    
    @property
    def Hf(self):
        return (self.chemicals.Hf * self.mol).sum()
    @property
    def Hc(self):
        return (self.chemicals.Hc * self.mol).sum()    
    @property
    def Hvap(self):
        return self.mixture.Hvap_at_TP(self.mol, self._TP)
    
    @property
    def C(self):
        return self.mixture.Cn_at_TP(self.mol, self._TP)
    
    ### Composition properties ###
    
    @property
    def z_mol(self):
        mol = self.mol
        F_mol = mol.sum()
        return mol / F_mol if F_mol else mol.copy()
    @property
    def z_mass(self):
        mass = self.chemicals.MW * self.mol
        F_mass = mass.sum()
        return mass / F_mass if F_mass else mass
    @property
    def z_vol(self):
        vol = self.vol.value
        F_vol = vol.sum()
        return vol / F_vol if F_vol else vol
    
    @property
    def MW(self):
        return self.F_mass / self.F_mol
    @property
    def V(self):
        mol = self.mol
        F_mol = mol.sum()
        return self.mixture.V_at_TP(self.phase, mol / F_mol, self._TP) if F_mol else 0
    @property
    def kappa(self):
        mol = self.mol
        F_mol = mol.sum()
        return self.mixture.kappa_at_TP(self.phase, mol / F_mol, self._TP) if F_mol else 0
    @property
    def Cn(self):
        mol = self.mol
        F_mol = mol.sum()
        return self.mixture.Cn_at_TP(self.phase, mol / F_mol, self._TP) if F_mol else 0
    @property
    def mu(self):
        mol = self.mol
        F_mol = mol.sum()
        return self.mixture.mu_at_TP(self.phase, mol / F_mol, self._TP) if F_mol else 0
    @property
    def sigma(self):
        mol = self.mol
        F_mol = mol.sum()
        return self.mixture.sigma_at_TP(mol / F_mol, self._TP) if F_mol else 0
    @property
    def epsilon(self):
        mol = self.mol
        F_mol = mol.sum()
        return self.mixture.epsilon_at_TP(mol / F_mol, self._TP) if F_mol else 0
    
    @property
    def Cp(self):
        return self.Cn / self.MW
    @property
    def alpha(self):
        return fn.alpha(self.kappa, self.rho, self.Cp)
    @property
    def rho(self):
        return fn.V_to_rho(self.V, self.MW)
    @property
    def nu(self):
        return fn.mu_to_nu(self.mu, self.rho)
    @property
    def Pr(self):
        return fn.Pr(self.Cp, self.mu, self.k)
    
    ### Stream methods ###
    
    def mix_from(self, others):
        if settings._debug: assert_same_chemicals(self, others)
        isa = isinstance
        self.mol[:] = sum([i.mol if isa(i, Stream) else i.mol.sum(0) for i in others])
        self.H = sum([i.H for i in others])
    
    def split_to(self, s1, s2, split):
        mol = self.mol
        s1.mol[:] = dummy = mol * split
        s2.mol[:] = mol - dummy
        
    def link(self, other, TP=True, flow=True, phase=True):
        if settings._debug:
            assert isinstance(other, self.__class__), "other must be of same type to link with"
        
        if TP and flow and phase:
            self._imol._data_cache = other._imol._data_cache
        else:
            self._imol._data_cache.clear()
            other._imol._data_cache.clear()
        
        if TP:
            self._TP = other._TP
        if flow:
            self._imol._data = other._imol._data
        if phase:
            self._imol._phase = other._imol._phase
            
    def unlink(self):
        self._imol._data_cache.clear()
        self._TP = self._TP.copy()
        self._imol._data = self._imol._data.copy()
        self._imol._phase = self._imol._phase.copy()
    
    def copy_like(self, other):
        self._imol.copy_like(other._imol)
        self._TP.copy_like(other._TP)
    
    def copy(self):
        cls = self.__class__
        new = cls.__new__(cls)
        new._ID = None
        new._thermo = self._thermo
        new._imol = self._imol.copy()
        new._TP = self._TP.copy()
        return new
    __copy__ = copy
    
    def empty(self):
        self._imol._data[:] = 0
    
    ### Equilibrium ###

    @property
    def vle(self):
        self.phases = 'gl'
        return self.vle

    @property
    def z_equilibrium_chemicals(self):
        mol = self.mol
        chemicals = self.chemicals
        indices = chemicals.equilibrium_indices(mol != 0)
        flow = mol[indices]
        netflow = flow.sum()
        assert netflow, "no equilibrium chemicals present"
        z = flow / netflow  
        chemicals_tuple = chemicals.tuple
        return z, [chemicals_tuple[i] for i in indices]
    
    @property
    def equilibrim_chemicals(self):
        chemicals = self.chemicals
        chemicals_tuple = chemicals.tuple
        indices = chemicals.equilibrium_indices(self.mol != 0)
        return [chemicals_tuple[i] for i in indices]
    
    @property
    def bubble_point(self):
        return eq.BubblePoint(self.equilibrim_chemicals, self._thermo)
    
    @property
    def dew_point(self):
        return eq.DewPoint(self.equilibrim_chemicals, self._thermo)
    
    @property
    def T_bubble(self):
        z, chemicals = self.z_equilibrium_chemicals
        bp = eq.BubblePoint(chemicals, self._thermo)
        return bp.solve_Ty(z, self.P)[0]
    
    @property
    def T_dew(self):
        z, chemicals = self.z_equilibrium_chemicals
        dp = eq.DewPoint(chemicals, self._thermo)
        return dp.solve_Tx(z, self.P)[0]
    
    @property
    def P_bubble(self):
        z, chemicals = self.z_equilibrium_chemicals
        bp = eq.BubblePoint(chemicals, self._thermo)
        return bp.solve_Py(z, self.T)[0]
    
    @property
    def P_dew(self):
        z, chemicals = self.z_equilibrium_chemicals
        dp = eq.DewPoint(chemicals, self._thermo)
        return dp.solve_Px(z, self.T)[0]
    
    ### Casting ###
    
    @property
    def phases(self):
        raise AttributeError(f"'{type(self).__name__}' object has no attribute 'phases'")
    @phases.setter
    def phases(self, phases):
        self.__class__ = multi_stream.MultiStream
        self._imol = self._imol.to_material_indexer(phases)
        self._vle = Cache(eq.VLE, self._imol, self._TP, thermo=self._thermo)
    
    ### Representation ###
    
    def _basic_info(self):
        return type(self).__name__ + ': ' + (self.ID or '') + '\n'
    
    def _info_phaseTP(self, phase, T_units, P_units):
        T = thermo_units.convert(self.T, 'K', T_units)
        P = thermo_units.convert(self.P, 'Pa', P_units)
        s = '' if isinstance(phase, str) else 's'
        return f" phase{s}: {repr(phase)}, T: {T:.5g} {T_units}, P: {P:.6g} {P_units}\n"
    
    def _info(self, T, P, flow, N):
        """Return string with all specifications."""
        from .material_indexer import nonzeros
        basic_info = self._basic_info()
        IDs = self.chemicals.IDs
        data = self.imol.data
        IDs, data = nonzeros(IDs, data)
        IDs = tuple(IDs)
        T_units, P_units, flow_units, N = self.display_units.get_units(T=T, P=P, flow=flow, N=N)
        basic_info += self._info_phaseTP(self.phase, T_units, P_units)
        len_ = len(IDs)
        if len_ == 0:
            return basic_info + ' flow: 0' 
        
        # Start of third line (flow rates)
        index, factor = self._get_indexer_and_factor(flow_units)
        beginning = f' flow ({flow_units}): '
            
        # Remaining lines (all flow rates)
        new_line_spaces = len(beginning) * ' '
        flow_array = factor * index[IDs]
        flowrates = ''
        lengths = [len(i) for i in IDs]
        maxlen = max(lengths) + 1
        _N = N - 1
        for i in range(len_-1):
            spaces = ' ' * (maxlen - lengths[i])
            if i == _N:
                flowrates += '...\n' + new_line_spaces
                break
            flowrates += IDs[i] + spaces + f' {flow_array[i]:.3g}\n' + new_line_spaces
        spaces = ' ' * (maxlen - lengths[len_-1])
        flowrates += IDs[len_-1] + spaces + f' {flow_array[len_-1]:.3g}'
        return (basic_info 
              + beginning
              + flowrates)

    def show(self, T=None, P=None, flow=None, N=None):
        """Print all specifications.
        
        Parameters
        ----------
        T: str, optional
            Temperature units.
        P: str, optional
            Pressure units.
        flow: str, optional
            Flow rate units.
        N: int, optional
            Number of compounds to display.
        
        Notes
        -----
        Default values are stored in `Stream.display_units`.
        
        """
        print(self._info(T, P, flow, N))
    _ipython_display_ = show
    
    def print(self):
        from .utils import repr_IDs_data, repr_kwarg
        chemical_flows = repr_IDs_data(self.chemicals.IDs, self.mol)
        price = repr_kwarg('price', self.price)
        print(f"{type(self).__name__}(ID={repr(self.ID)}, phase={repr(self.phase)}, T={self.T:.2f}, "
              f"P={self.P:.6g}{price}{chemical_flows})")
        
from . import multi_stream
del registered