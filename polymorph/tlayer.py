# File from polymorph project
# Copyright (C) 2020 Santiago Hernandez Ramos <shramos@protonmail.com>
# For more information about the project: https://github.com/shramos/polymorph

from collections import OrderedDict
from polymorph.tfield import TField
from termcolor import colored
from construct import *
from texttable import Texttable
from polymorph.converter import Converter


class TLayer(object):
    """Class that represents a layer within a `Template`."""

    def __init__(self, name, pkt_raw, lslice, fields=None):
        """Initialization method of the class.

        Parameters
        ----------
        name : str
            Name of the layer.
        pkt_raw : :obj:`bytes`
            Packet content in bytes.
        lslice : :obj:`slice`
            Slice representing the position of the `TLayer` in the raw
            packet data.
        fields : :obj:`OrderedDict`, optional
            Dictionary with the fields of the layer of the form
            {fieldname : `TField`}.

        """
        self._fields = fields if fields else OrderedDict()
        self._name = name.upper()
        self._pkt_raw = pkt_raw
        self._lslice = lslice
        self._structs = OrderedDict()
        self._saved_structs = OrderedDict()
        # This constants will help constructing the structs
        self._nums = {'1': {'Ftype.FT_INT_BE': Int8ub,
                            'Ftype.FT_INT_LE': Int8ul},
                      '2': {'Ftype.FT_INT_BE': Int16ub,
                            'Ftype.FT_INT_LE': Int16ul},
                      '3': {'Ftype.FT_INT_BE': Int24ub,
                            'Ftype.FT_INT_LE': Int24ul},
                      '4': {'Ftype.FT_INT_BE': Int32ub,
                            'Ftype.FT_INT_LE': Int32ul}}

    def __repr__(self):
        return "<tlayer.TLayer(%s): %s>" % (
            self._name, " ".join([f.name for f in self._fields.values()]))

    def __getitem__(self, field):
        return self.getfield(field)

    @property
    def name(self):
        """str: Name of the `TLayer`."""
        return self._name

    @name.setter
    def name(self, value):
        self._name = value.upper()

    @property
    def slice(self):
        """:obj:`slice`: Slice that represents the position of the `TLayer`
        in the raw payload.

        """
        return self._lslice

    @property
    def pkt_raw(self):
        """:obj:`bytearray` : Packet content in raw (bytes representation)."""
        return self._pkt_raw

    @property
    def fields(self):
        """:obj:`list` of :obj:`TField`: Obtain all the fields of the
        `TLayer`."""
        return self.getfields()

    @fields.setter
    def fields(self, fields):
        self._fields = fields

    def add_struct(self, fname, fdeps, start_byte, expression):
        """This function creates a structure that relates a field to other
        fields of the layer, so that its value can be calculated dynamically
        at run time. Perform additional processing before sending the data
        to create_struct.

        Parameters
        ----------
        fname: :obj:`str`
            Name of the field which value will be recalculated.
        fdeps: :obj:`list` of :obj:`str`
            Dependen fields.
        start_byte: :obj:`str`
            Byte in which the value of the main field begins. Must be a `str`.
            Fields must be preceded by 'this'. It can be a complex expression:
            '70 - this.field_len'
        expression: :obj:`str`
            Expression with which the new field value will be calculated
            dynamically. Fields must be preceded by 'this'. Can be complex:
            'this.field_len - this.field2_len - 2'

        """
        # This is used for saving the structs in the template
        self._saved_structs[fname] = {"fdeps": fdeps,
                                      "sb": start_byte,
                                      "exp": expression}
        # We obtain the dependent fields from the field name
        dep_fields = [self.getfield(f) for f in fdeps]
        main_field = self.getfield(fname)
        # Construction of the structure
        st = self.create_struct(main_field, dep_fields, start_byte, expression)
        self._structs[fname] = st

    def test_struct(self, fname):
        """Tests de result of the Struct for a particula `TField`.

        Parameters
        ----------
        tfieldname: :obj:`str`
            Name of the `TField` to be tested.

        """
        cv = Converter()
        field = self.getfield(fname)
        if fname in self._structs:
            fraw = self._structs[fname].parse(self._pkt_raw).__getitem__(fname)
            return cv.get_frepr(field.type, fraw, len(fraw), None, fname)

    def del_struct(self, tfieldname):
        """Deletes a `Struct` from a `TField`/

        Parameters
        ----------
        tfieldname: :obj:`str`
            Name of the `TField` to be deleted.

        """
        if tfieldname in self._structs:
            del self._structs[tfieldname]

    def get_struct(self, tfieldname):
        """Returns the `Struct` for a particula `TField`.

        Parameters
        ----------
        tfieldname: :obj:`str`
            Name of the `TField`.

        Returns
        -------
        :obj:`Struct`

        """
        if tfieldname in self._structs:
            return self._structs[tfieldname]

    def show_structs(self, tfname):
        """Pretty Print of the Structs of a `TField`.

        Parameters
        ----------
        tfname: :obj:`str`
            Name of the `TField`.

        """
        if tfname not in self._structs:
            return
        t = Texttable()
        rows = [["Field", "Position"]]
        sb = self._saved_structs[tfname]['sb'].replace(
            "this.", "").replace(".", "_")
        e = self._saved_structs[tfname]['exp'].replace(
            "this.", "").replace(".", "_")
        exps = [sb, e] if not sb.isdecimal() else [e]
        start = 0
        stop = 0
        for s in self._structs[tfname].subcons:
            try:
                start = stop
                stop = start + s.sizeof()
                rows.append([s.name, (start, stop)])
            except:
                start = stop
                stop = exps.pop(0)
                rows.append([s.name, (start, stop)])

        print(colored('\n--- Struct for %s' % tfname,
                      'cyan', attrs=['bold']))
        t.add_rows(rows)
        print(t.draw(), "\n")

    def get_structs(self):
        """Returns the `Struct` for all the `Tfields` in the `TLayer`.

        Returns
        -------
        :obj:`OrderedDict`

        """
        return self._structs

    def is_struct(self, tfieldname):
        """Returns True if the `TField` has a particular `Struct` associated.

        Parameters
        ----------
        tfieldname : :obj:`str`
            Name of the `TField`.

        Returns
        -------
        :obj:`bool`
            True if the `TField` has a `Struct` object associated,
            False otherwise.

        """
        return tfieldname in self._structs

    def create_struct(self, tfield, fdeps, start_byte, expression):
        """This function creates a structure that relates a field to other
         fields of the layer, so that its value can be calculated dynamically
          at run time.

        Parameters
        ----------
        tfield : :obj:`TField`
            Field for which the new value will be calculated.
        fdeps: :obj:`list` of :obj:`TField`
            List of fields on which the previous field depends.
        start_byte: :obj:`str`
            Byte in which the value of the main field begins. Must be a `str`.
            Fields must be preceded by 'this'. It can be a complex expression:
            '70 - this.field_len'
        expression: :obj:`str`
            Expression with which the new field value will be calculated
            dynamically. Fields must be preceded by 'this'. Can be complex:
            'this.field_len - this.field2_len - 2'

        Returns
        -------
        :obj:`Struct`
            Structure that allows to parse the raw bytes of the packet and
             return the exact value of the field.

        """
        # We sort the dependent fields by position in the packet bytes
        ordered_list = sorted(fdeps, key=lambda f: f.slice.start)
        # Building the Struct dependencies
        st = Struct()
        stop_byte = 0
        for field in ordered_list:
            st_byte = field.slice.start - stop_byte
            stop_byte = field.slice.stop
            # Adding padding to the Struct
            fname = field.name.replace(".", "_") + "pad"
            st += fname / Bytes(st_byte)
            # Adding the field
            st += field.name.replace(".", "_") / \
                self._nums[str(field.size)][str(field.type)]
        # Building the struct main field
        # Adding paddig to the struct
        fname = tfield.name.replace(".", "_") + "pad"
        st += fname.replace(".", "_") / Bytes(
            eval(start_byte.replace(".", "_").replace("this_", "this.")) - stop_byte)
        # Adding the field
        st += tfield.name / \
            Bytes(eval(expression.replace(".", "_").replace("this_", "this.")))
        return st

    def addfield(self, field):
        """Adds a `TField` to the actual `TLayer`.

        Note
        ----
        If a `TField` with the same name is alreadry in the `TLayer`,
        the name of the field is modified by concatenating a number.

        Parameters
        ----------
        field : :obj:`TField`
            Field that will be added to the `TLayer`.

        """
        fname = field.name
        if fname not in self._fields:
            self._fields[fname] = field
        else:
            new_fname = self._new_fname(fname, self._fields)
            field.name = new_fname
            self._fields[new_fname] = field

    def _new_fname(self, fname, all_fields):
        """Generates new names for fields with duplicate name."""
        if fname in all_fields:
            if fname[-1].isnumeric():
                return self._new_fname(
                    fname[:-1] + str(int(fname[-1]) + 1), all_fields)
            else:
                return self._new_fname(fname + str(2), all_fields)
        else:
            return fname

    def delfield(self, field):
        """Deletes a `TField` from the `TLayer`.

        Parameters
        ----------
        field : :obj:`TField`, str
            Field that will be deleted from the `TLayer`.

        """
        if type(field) is TField:
            self._fields.pop(field.name)
        elif type(field) is str:
            self._fields.pop(field.lower())

    def getfield(self, fieldname):
        """Obtain a `TField` from the `TLayer`.

        Parameters
        ----------
        fieldname : str
            String with the name of a `TField`.

        Returns
        -------
        :obj:`TField`
            The object that has the name specified.
        :obj:`None`
            if there is no field with the specified name

        """
        if self.isfield(fieldname):
            return self._fields[fieldname.lower()]
        else:
            return None

    def getfields(self):
        """Get all the `TFields` in the `TLayer`.

        Returns
        -------
        :obj:`list` of :obj:`TFields`
            List of all `TField` in the `TLayer`.

        """
        return list(self._fields.values())

    def isfield(self, fieldname):
        """Check if there is a `TField` with that name in the `TLayer`.

        Parameters
        ----------
        fieldname : str
            Name of the field.

        Returns
        -------
        bool
            True if exists, False if not.

        """
        return fieldname.lower() in self._fields

    def fieldnames(self):
        """Returns the names of the `TField` of which the `TLayer` is formed.

        Returns
        -------
        :obj:`list` of :obj:`str`
            List with the names of the `TField` in `str`

        """
        return [f.name for f in self.getfields()]

    def show(self):
        """Pretty print of the `TLayer` object with types."""
        print('\n', colored("---[ %s ]---" %
                            self._name, 'white', attrs=['bold']), sep="")
        for field in self.fields:
            print('{0: <35}'.format(colored(str(field.type)[6:], 'cyan', attrs=[
                  'bold']) + " " + field.name) + "= " + colored(str(field.value), 'cyan'))
        print()

    def dict(self):
        """Build a dictionary with all the elements of the `TLayer`.

        Returns
        -------
        :obj:`dict`
            Dictionary with all the fields and attributes of the `TLayer`.

        """
        return OrderedDict([
            ("name", self._name),
            ("lslice", str(self._lslice)),
            ("fields", [f.dict() for f in self._fields.values()]),
            ("structs", self._saved_structs)
        ])
