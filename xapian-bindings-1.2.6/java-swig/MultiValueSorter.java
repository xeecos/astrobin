/* ----------------------------------------------------------------------------
 * This file was automatically generated by SWIG (http://www.swig.org).
 * Version 2.0.5
 *
 * Do not make changes to this file unless you know what you are doing--modify
 * the SWIG interface file instead.
 * ----------------------------------------------------------------------------- */


public class MultiValueSorter extends Sorter {
  private long swigCPtr;

  public MultiValueSorter(long cPtr, boolean cMemoryOwn) {
    super(XapianJNI.MultiValueSorter_SWIGUpcast(cPtr), cMemoryOwn);
    swigCPtr = cPtr;
  }

  public static long getCPtr(MultiValueSorter obj) {
    return (obj == null) ? 0 : obj.swigCPtr;
  }

  protected void finalize() {
    delete();
  }

  public synchronized void delete() {
    if (swigCPtr != 0) {
      if (swigCMemOwn) {
        swigCMemOwn = false;
        XapianJNI.delete_MultiValueSorter(swigCPtr);
      }
      swigCPtr = 0;
    }
    super.delete();
  }

  public MultiValueSorter() {
    this(XapianJNI.new_MultiValueSorter(), true);
  }

  public String apply(Document doc) {
    return XapianJNI.MultiValueSorter_apply(swigCPtr, this, Document.getCPtr(doc), doc);
  }

  public void add(int slot, boolean forward) {
    XapianJNI.MultiValueSorter_add__SWIG_0(swigCPtr, this, slot, forward);
  }

  public void add(int slot) {
    XapianJNI.MultiValueSorter_add__SWIG_1(swigCPtr, this, slot);
  }

}